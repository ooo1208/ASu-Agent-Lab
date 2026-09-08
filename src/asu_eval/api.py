"""FastAPI router factory. Authentication comes exclusively from the host app."""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .store import EvaluationStore


class SnapshotBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trace_id: str = Field(min_length=1, max_length=256)
    session_id: str = Field(min_length=1, max_length=256)
    version: str = Field(min_length=1, max_length=256)
    run_id: str | None = Field(default=None, min_length=1, max_length=1024)
    actual: dict[str, Any]
    expected: dict[str, Any]
    input_data: Any = None


class FeedbackBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rating: int = Field(ge=0, le=1, strict=True)
    comment: str = Field(default="", max_length=4000)
    corrected_expected: dict[str, Any] | None = None


class PromoteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_version: str = Field(min_length=1, max_length=100)


def user_id_of(principal: Any) -> str:
    if isinstance(principal, str):
        value = principal
    elif isinstance(principal, dict):
        value = principal.get("user_id") or principal.get("id")
    else:
        value = getattr(principal, "user_id", None) or getattr(principal, "id", None)
    if not isinstance(value, str) or not value:
        raise HTTPException(status_code=401, detail="Authenticated user ID is required")
    return value


def create_router(store: EvaluationStore, auth_dependency: Callable[..., Any], *, prefix: str = "/evaluation") -> APIRouter:
    """Mount under /api if needed. No endpoint accepts a caller-supplied user_id."""
    router = APIRouter(prefix=prefix, tags=["evaluation"])

    def owner(principal: Any = Depends(auth_dependency)) -> str:
        return user_id_of(principal)

    @router.post("/jobs", status_code=202)
    def submit(body: SnapshotBody, user_id: str = Depends(owner)) -> dict[str, str]:
        try:
            job_id = store.enqueue(user_id=user_id, **body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        return {"job_id": job_id}

    @router.get("/jobs")
    def jobs(limit: int = Query(default=50, ge=1, le=200), user_id: str = Depends(owner)) -> list[dict[str, Any]]:
        return store.list_jobs(user_id, limit=limit)

    @router.get("/jobs/{job_id}")
    def job(job_id: str, user_id: str = Depends(owner)) -> dict[str, Any]:
        result = store.get_job(user_id, job_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return result

    @router.post("/jobs/{job_id}/retry", status_code=202)
    def retry(job_id: str, user_id: str = Depends(owner)) -> dict[str, str]:
        try:
            store.retry_failed(user_id, job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found") from None
        return {"job_id": job_id, "status": "failed items queued for retry"}

    @router.post("/jobs/{job_id}/feedback", status_code=201)
    def feedback(job_id: str, body: FeedbackBody, user_id: str = Depends(owner)) -> dict[str, str]:
        try:
            feedback_id = store.add_feedback(user_id=user_id, job_id=job_id, **body.model_dump())
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        return {"feedback_id": feedback_id}

    @router.get("/jobs/{job_id}/feedback")
    def feedback_list(job_id: str, user_id: str = Depends(owner)) -> list[dict[str, Any]]:
        try:
            return store.list_feedback(user_id, job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found") from None

    @router.post("/feedback/{feedback_id}/promote", status_code=201)
    def promote(feedback_id: str, body: PromoteBody, user_id: str = Depends(owner)) -> dict[str, str]:
        try:
            case_id = store.promote_feedback(user_id=user_id, feedback_id=feedback_id, dataset_version=body.dataset_version)
        except KeyError:
            raise HTTPException(status_code=404, detail="Feedback not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        return {"case_id": case_id}

    @router.get("/golden/{dataset_version}")
    def golden(dataset_version: str, user_id: str = Depends(owner)) -> dict[str, Any]:
        return store.export_golden(user_id, dataset_version)

    return router
