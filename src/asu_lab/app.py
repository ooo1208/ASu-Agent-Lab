"""Local synthetic demonstration using the real evidence/evaluation/business services."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, ConfigDict

from asu_eval.api import create_router
from asu_finance import create_finance_router
from asu_lab.local_auth import LocalState
from asu_lab.observability import observe_sse
from asu_lab.services import evaluation_store, evidence_store, task_context_store
from asu_lab.settings import database_path


class AuthBody(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=50)


class ChatBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=10000)
    thread_id: str | None = Field(default=None, max_length=100)


class ResumeBody(BaseModel):
    resume: dict


def event(kind: str, **fields):
    return "data: " + json.dumps({"type": kind, **fields}, ensure_ascii=False) + "\n\n"


def create_app():
    state = LocalState(database_path("demo"))
    app = FastAPI(title="ERP_OPENCLAW — local synthetic demo", version="0.1.0")
    bearer = HTTPBearer(auto_error=False)

    def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        user = state.authenticate(credentials.credentials) if credentials and credentials.scheme.lower() == "bearer" else None
        if not user:
            raise HTTPException(401, "请先登录", headers={"WWW-Authenticate": "Bearer"})
        return user

    def owned(user, thread_id):
        try:
            return state.thread(user.user_id, thread_id)
        except PermissionError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/health")
    @app.get("/api/lab/status")
    def status():
        return {"status": "healthy", "mode": "demo", "model_calls_enabled": False, "project": "ERP_OPENCLAW"}

    @app.post("/api/auth/register")
    def register(body: AuthBody):
        try:
            user = state.register(body.username, body.password, body.display_name)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"access_token": state.issue(user), "token_type": "bearer", "user": asdict(user)}

    @app.post("/api/auth/login")
    def login(body: AuthBody):
        user = state.login(body.username, body.password)
        if not user:
            raise HTTPException(401, "用户名或密码不正确")
        return {"access_token": state.issue(user), "token_type": "bearer", "user": asdict(user)}

    @app.get("/api/auth/me")
    def me(user=Depends(current_user)):
        return asdict(user)

    @app.get("/api/history")
    def history(page: int = Query(default=1, ge=1), limit: int = Query(default=20, ge=1, le=100), user=Depends(current_user)):
        with state.connect() as db:
            count = db.execute("SELECT COUNT(*) FROM threads WHERE user_id=?", (user.user_id,)).fetchone()[0]
            rows = db.execute("SELECT id,title,updated FROM threads WHERE user_id=? ORDER BY updated DESC LIMIT ? OFFSET ?", (user.user_id, limit, (page-1)*limit)).fetchall()
        return {"sessions": [{"thread_id": r["id"], "title": r["title"], "updated_at": datetime.fromtimestamp(r["updated"], timezone.utc).isoformat()} for r in rows], "total": count, "page": page, "limit": limit}

    @app.get("/api/history/{thread_id}/messages")
    def messages(thread_id: str, user=Depends(current_user)):
        row = owned(user, thread_id)
        return {"thread_id": thread_id, "messages": json.loads(row["messages"])}

    @app.delete("/api/history/{thread_id}")
    def delete(thread_id: str, user=Depends(current_user)):
        owned(user, thread_id)
        with state.connect() as db:
            db.execute("DELETE FROM threads WHERE id=? AND user_id=?", (thread_id, user.user_id))
        return {"success": True}

    @app.patch("/api/history/{thread_id}")
    def title(thread_id: str, title: str = Query(min_length=1, max_length=60), user=Depends(current_user)):
        owned(user, thread_id)
        with state.connect() as db:
            db.execute("UPDATE threads SET title=? WHERE id=? AND user_id=?", (title, thread_id, user.user_id))
        return {"success": True}

    @app.get("/api/tasks")
    def tasks(user=Depends(current_user)):
        return {"tasks": [], "mode": "demo", "description": "独立多 Agent 后台分析在 live 模式启用；评估 Worker 在两种模式均可运行。"}

    @app.get("/api/chat/{thread_id}")
    def chat_state(thread_id: str, user=Depends(current_user)):
        row = owned(user, thread_id)
        return {"thread_id": thread_id, "pending": json.loads(row["pending"]) if row["pending"] else None}

    async def chat_events(user, thread_id, message):
        state.append(user.user_id, thread_id, "user", message)
        if "演示下单" in message:
            # The explicit demo command fixes a synthetic item; no model guesses identifiers.
            quantity = int(re.search(r"(\d+)\s*(?:个|件|份)", message).group(1)) if re.search(r"(\d+)\s*(?:个|件|份)", message) else 1
            if not 1 <= quantity <= 100:
                yield event("error", message="演示数量须为 1–100")
                return
            pending = {"status": "awaiting_approval", "request_id": uuid.uuid4().hex, "payload": {"orderDetail": [{"partId": 1, "quantity": quantity, "unitPrice": "38.50"}], "remark": "ASu 本地合成演示"}}
            try:
                state.set_pending(user.user_id, thread_id, pending)
            except ValueError as exc:
                yield event("error", message=str(exc))
                return
            text = f"合成演示：为示例陶瓷刹车片创建 {quantity} 件采购单，单价 38.50。批准后才写入本地 Java ERP。"
            yield event("token", content=text, source="demo")
            state.append(user.user_id, thread_id, "assistant", text)
            yield event("interrupt", thread_id=thread_id, interrupt_type="hitl_approval", action_requests=[{"name": "order_create", "args": pending["payload"], "description": text}], review_configs=[{"action_name": "order_create", "allowed_decisions": ["approve", "reject"]}])
            return
        query = message.replace("查找", "").replace("检索", "").strip()[:1000]
        hits = evidence_store().search(user.user_id, query, limit=3) if query else []
        if hits:
            tool_id = uuid.uuid4().hex
            yield event("tool_start", tool_call_id=tool_id, tool_name="evidence_search", source="demo")
            yield event("tool_args", tool_call_id=tool_id, args=json.dumps({"query": query}, ensure_ascii=False), source="demo")
            yield event("tool_result", tool_call_id=tool_id, text=json.dumps(hits, ensure_ascii=False), source="demo")
            text = "以下为当前用户文档的检索结果（本地演示未调用大模型）：\n\n" + "\n\n".join(str(h.get("text", h.get("content", "")))[:900] + "\n引用：" + str(h.get("citation_id", "")) for h in hits)
        else:
            text = "当前是本地合成演示，不调用大模型。请先在「证据工作台」导入材料，再输入其中的关键词检索；也可以在「评估中心」创建评估并查看 Worker 结果。输入“演示下单 2 件”可体验本地 Java ERP 的审批流程。完整多 Agent 分析请使用 live 模式。"
        state.append(user.user_id, thread_id, "assistant", text)
        yield event("token", content=text, source="demo")
        yield event("done", thread_id=thread_id, content=text)

    @app.post("/api/chat/stream")
    def chat(body: ChatBody, user=Depends(current_user)):
        thread_id = body.thread_id or uuid.uuid4().hex
        try:
            state.claim_thread(user.user_id, thread_id, body.message)
        except PermissionError as exc:
            raise HTTPException(404, str(exc)) from exc
        source = observe_sse(chat_events(user, thread_id, body.message), user_id=user.user_id, thread_id=thread_id, input_text=body.message)
        return StreamingResponse(source, media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/chat/{thread_id}/resume")
    def resume(thread_id: str, body: ResumeBody, user=Depends(current_user)):
        owned(user, thread_id)
        decisions = body.resume.get("decisions", [])
        if not isinstance(decisions, list) or len(decisions) != 1 or not isinstance(decisions[0], dict) or decisions[0].get("type") not in {"approve", "reject"}:
            raise HTTPException(422, "请选择批准或拒绝")
        approved = decisions[0]["type"] == "approve"
        try:
            pending = state.take_pending(user.user_id, thread_id, approved)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

        async def resume_events():
            if not approved:
                text = "已拒绝。本次演示未调用 ERP 写接口。"
            else:
                tool_id = uuid.uuid4().hex
                yield event("tool_start", tool_call_id=tool_id, tool_name="order_create", source="demo")
                yield event("tool_args", tool_call_id=tool_id, args=json.dumps(pending["payload"]), source="demo")
                try:
                    headers = {"Idempotency-Key": pending["request_id"]}
                    if os.getenv("ERP_API_KEY"):
                        headers["X-API-Key"] = os.environ["ERP_API_KEY"]
                    async with httpx.AsyncClient(timeout=15) as client:
                        response = await client.post(os.getenv("ERP_API_BASE_URL", "http://127.0.0.1:8080/api") + "/orders/create", json=pending["payload"], headers=headers)
                        response.raise_for_status()
                        result = response.json(parse_float=str)
                    if result.get("code") != 200:
                        raise ValueError(result.get("message", "ERP 拒绝操作"))
                    pending["status"] = "completed"
                    pending["result"] = result.get("data")
                    yield event("tool_result", tool_call_id=tool_id, text=json.dumps(result, ensure_ascii=False), source="demo")
                    order = result.get("data", {})
                    text = f"本地 ERP 已创建合成采购订单。\n\n- 订单编号：{order.get('orderNumber', order.get('id', '见工具结果'))}\n- 合计：{order.get('totalAmount', '见工具结果')} 元\n- 当前状态：待审核\n\n订单详情已保留，可在工具结果中查看。"
                except Exception as exc:
                    pending["status"] = "failed" if isinstance(exc, (httpx.ConnectTimeout, httpx.ConnectError, httpx.HTTPStatusError)) else "outcome_unknown"
                    yield event("tool_result", tool_call_id=tool_id, text=json.dumps({"error": type(exc).__name__, "status": pending["status"]}), source="demo")
                    text = "本次未获得成功确认。请检查 Java ERP 是否启动，并核对订单状态。系统不会自动重放写操作。"
                state.set_pending(user.user_id, thread_id, pending)
            state.append(user.user_id, thread_id, "assistant", text)
            yield event("token", content=text, source="demo")
            yield event("done", thread_id=thread_id, content=text)

        return StreamingResponse(observe_sse(resume_events(), user_id=user.user_id, thread_id=thread_id, approved=approved), media_type="text/event-stream")

    app.include_router(create_finance_router(evidence_store(), current_user), prefix="/api")
    app.include_router(create_router(evaluation_store(), current_user), prefix="/api")
    app.state.local_state = state
    return app
