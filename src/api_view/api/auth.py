"""用户注册、登录和当前身份接口。"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api_view.auth_service import (
    AuthenticatedUser,
    authenticate_user,
    create_access_token,
    get_current_user,
    register_user,
)

router = APIRouter()


class Credentials(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)


class RegisterRequest(Credentials):
    display_name: str | None = Field(None, min_length=1, max_length=50)


def _user_payload(user: AuthenticatedUser) -> dict:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "display_name": user.display_name,
    }


def _login_response(user: AuthenticatedUser) -> dict:
    token, expires_in = create_access_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "user": _user_payload(user),
    }


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest):
    try:
        return _login_response(
            register_user(request.username, request.password, request.display_name)
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/auth/login")
async def login(request: Credentials):
    user = authenticate_user(request.username, request.password)
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return _login_response(user)


@router.get("/auth/me")
async def me(user: AuthenticatedUser = Depends(get_current_user)):
    return _user_payload(user)
