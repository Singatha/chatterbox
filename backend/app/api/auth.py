from fastapi import APIRouter, status

from app.api.dependencies import CurrentUser, DbSession
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, session: DbSession) -> TokenResponse:
    return await AuthService(session).register(data)


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, session: DbSession) -> TokenResponse:
    return await AuthService(session).login(data)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, session: DbSession) -> TokenResponse:
    return await AuthService(session).refresh(data.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(data: LogoutRequest, session: DbSession) -> None:
    await AuthService(session).logout(data.refresh_token)


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)

