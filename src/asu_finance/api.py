"""Optional FastAPI routes. Caller supplies and owns the authentication dependency."""

import base64
import binascii
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .calculator import CalculationError, calculate, evaluate_program
from .evidence import EvidenceError, EvidenceStore, MAX_DOCUMENT_BYTES
from .review import verify_claim


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentRequest(StrictRequest):
    filename: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=14 * 1024 * 1024)
    encoding: Literal["utf-8", "base64"] = "utf-8"
    namespace: str = Field(default="default", min_length=1, max_length=200)


class CalculationRequest(StrictRequest):
    operation: str
    values: dict[str, str]


class ProgramRequest(StrictRequest):
    program: str = Field(min_length=1, max_length=4096)


class ReviewRequest(CalculationRequest):
    reported_value: str
    citation_ids: list[str] = Field(min_length=1, max_length=20)
    namespace: str = Field(default="default", min_length=1, max_length=200)


def _owner(principal) -> str:
    user_id = principal if isinstance(principal, str) else (principal.get("user_id") if isinstance(principal, dict) else getattr(principal, "user_id", None))
    if not isinstance(user_id, str) or not user_id.strip():
        raise HTTPException(status_code=401, detail="Authentication dependency must provide a trusted user_id.")
    return user_id


def create_finance_router(store: EvidenceStore, auth_dependency, *, prefix: str = "/finance") -> APIRouter:
    """Mount with app.include_router(...). Never pass an unauthenticated body/query id as auth."""
    router = APIRouter(prefix=prefix, tags=["financial-evidence"])

    @router.post("/documents", status_code=201)
    def ingest(request: DocumentRequest, principal=Depends(auth_dependency)):
        owner = _owner(principal)
        try:
            data = request.content
            if request.encoding == "base64":
                data = base64.b64decode(data, validate=True)
            if len(data.encode("utf-8") if isinstance(data, str) else data) > MAX_DOCUMENT_BYTES:
                raise EvidenceError("Document exceeds 10 MiB.")
            return store.ingest(owner, request.filename, data, namespace=request.namespace)
        except (EvidenceError, binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/search")
    def search(q: str = Query(min_length=1, max_length=1000), namespace: str = "default",
               limit: int = Query(default=5, ge=1, le=20), principal=Depends(auth_dependency)):
        try:
            return {"results": store.search(_owner(principal), q, namespace=namespace, limit=limit), "retrieval": "SQLite FTS5 lexical"}
        except EvidenceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/citations/{citation_id}")
    def citation(citation_id: str, namespace: str = "default", principal=Depends(auth_dependency)):
        try:
            result = store.get_citation(_owner(principal), citation_id, namespace=namespace)
        except EvidenceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(status_code=404, detail="Citation unavailable in this namespace.")
        return result

    @router.delete("/documents/{document_id}")
    def delete(document_id: str, namespace: str = "default", principal=Depends(auth_dependency)):
        try:
            removed = store.delete_document(_owner(principal), document_id, namespace=namespace)
        except EvidenceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not removed:
            raise HTTPException(status_code=404, detail="Document unavailable in this namespace.")
        return {"deleted": True, "document_id": document_id}

    @router.post("/calculate")
    def calculation(request: CalculationRequest, principal=Depends(auth_dependency)):
        _owner(principal)
        try:
            return calculate(request.operation, request.values)
        except CalculationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/program")
    def program(request: ProgramRequest, principal=Depends(auth_dependency)):
        _owner(principal)
        try:
            return evaluate_program(request.program)
        except CalculationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/review")
    def review(request: ReviewRequest, principal=Depends(auth_dependency)):
        try:
            return verify_claim(store, _owner(principal), operation=request.operation, values=request.values,
                                reported_value=request.reported_value, citation_ids=request.citation_ids,
                                namespace=request.namespace)
        except (CalculationError, EvidenceError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return router
