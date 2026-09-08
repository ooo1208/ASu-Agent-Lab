"""Signed claims used to bind Agent Protocol runs to one user's sandbox."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import jwt

CLAIM_PURPOSE = "async-user-sandbox"
JWT_ALGORITHM = "HS256"
JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "local-development-secret-key-change-before-production-2026",
)


def create_async_sandbox_claim(
    *, user_id: str, sandbox_id: str, task_id: str,
) -> str:
    """Create a short-lived, tamper-proof sandbox binding for one async task."""
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": user_id,
            "sandbox_id": sandbox_id,
            "task_id": task_id,
            "purpose": CLAIM_PURPOSE,
            "iat": now,
            "exp": now + timedelta(hours=6),
        },
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def decode_async_sandbox_claim(token: str, *, task_id: str) -> tuple[str, str]:
    """Verify a claim and return its trusted ``(user_id, sandbox_id)`` binding."""
    payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    if payload.get("purpose") != CLAIM_PURPOSE:
        raise ValueError("Invalid async sandbox claim purpose")
    if payload.get("task_id") != task_id:
        raise ValueError("Async sandbox claim does not match this task")

    user_id = str(payload.get("sub") or "").strip()
    sandbox_id = str(payload.get("sandbox_id") or "").strip()
    if not user_id or not sandbox_id:
        raise ValueError("Async sandbox claim is missing user or sandbox identity")
    return user_id, sandbox_id
