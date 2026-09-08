"""MongoDB 用户认证与 JWT 身份解析。"""

import hashlib
import hmac
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from bson import ObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pymongo import ASCENDING, MongoClient
from pymongo.errors import DuplicateKeyError

from api_view.web_config import (
    JWT_ALGORITHM,
    JWT_EXPIRE_HOURS,
    JWT_SECRET_KEY,
    MONGODB_DB_NAME,
    MONGODB_URI,
)

USERS_COLLECTION = "users"
_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_\-\u4e00-\u9fff]{3,32}$")
_security = HTTPBearer(auto_error=False)
_client: MongoClient | None = None


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    username: str
    display_name: str


def initialize_auth() -> None:
    """连接 MongoDB，并创建用户唯一索引。"""
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI)
    collection = _client[MONGODB_DB_NAME][USERS_COLLECTION]
    collection.create_index([("username_normalized", ASCENDING)], unique=True)


def _users():
    if _client is None:
        initialize_auth()
    return _client[MONGODB_DB_NAME][USERS_COLLECTION]


def _normalize_username(username: str) -> str:
    value = username.strip()
    if not _USERNAME_PATTERN.fullmatch(value):
        raise ValueError("用户名须为 3-32 位中文、字母、数字、下划线或连字符")
    return value.lower()


def _hash_password(password: str, *, salt: bytes | None = None) -> str:
    if len(password) < 8 or len(password) > 128:
        raise ValueError("密码长度须为 8-128 位")
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32
    )
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, expected_hex = stored.split("$")
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(expected_hex)),
        )
        return hmac.compare_digest(actual.hex(), expected_hex)
    except (TypeError, ValueError):
        return False


def _public_user(document: dict) -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=str(document["_id"]),
        username=document["username"],
        display_name=document.get("display_name") or document["username"],
    )


def register_user(username: str, password: str, display_name: str | None) -> AuthenticatedUser:
    normalized = _normalize_username(username)
    password_hash = _hash_password(password)
    clean_display_name = (display_name or username).strip()
    if not clean_display_name or len(clean_display_name) > 50:
        raise ValueError("显示名称长度须为 1-50 位")
    now = datetime.now(timezone.utc)
    document = {
        "username": username.strip(),
        "username_normalized": normalized,
        "display_name": clean_display_name,
        "password_hash": password_hash,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    try:
        result = _users().insert_one(document)
    except DuplicateKeyError as exc:
        raise ValueError("用户名已存在") from exc
    document["_id"] = result.inserted_id
    return _public_user(document)


def authenticate_user(username: str, password: str) -> AuthenticatedUser | None:
    try:
        normalized = _normalize_username(username)
    except ValueError:
        return None
    document = _users().find_one({"username_normalized": normalized, "status": "active"})
    if not document or not _verify_password(password, document.get("password_hash", "")):
        return None
    return _public_user(document)


def create_access_token(user: AuthenticatedUser) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=JWT_EXPIRE_HOURS)
    token = jwt.encode(
        {
            "sub": user.user_id,
            "username": user.username,
            "display_name": user.display_name,
            "iat": now,
            "exp": expires,
            "type": "access",
        },
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )
    return token, int((expires - now).total_seconds())


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> AuthenticatedUser:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录状态无效或已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )
        user_id = payload.get("sub")
        if not user_id or not ObjectId.is_valid(user_id):
            raise unauthorized
        document = _users().find_one({"_id": ObjectId(user_id), "status": "active"})
        if not document:
            raise unauthorized
        return _public_user(document)
    except HTTPException:
        raise
    except jwt.PyJWTError as exc:
        raise unauthorized from exc
