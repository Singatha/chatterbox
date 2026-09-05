from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.token_repository import TokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.tokens = TokenRepository(session)

    async def register(self, data: RegisterRequest) -> TokenResponse:
        if await self.users.email_or_username_exists(data.email, data.username):
            raise AppError(409, "USER_ALREADY_EXISTS", "Email or username is already registered")

        user = User(
            username=data.username,
            email=data.email,
            password_hash=hash_password(data.password),
        )
        self.users.add(user)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                409, "USER_ALREADY_EXISTS", "Email or username is already registered"
            ) from exc
        response = await self._issue_token_pair(user)
        await self.session.commit()
        return response

    async def login(self, data: LoginRequest) -> TokenResponse:
        user = await self.users.get_by_email_or_username(data.login)
        if user is None or not verify_password(data.password, user.password_hash):
            raise AppError(401, "INVALID_CREDENTIALS", "Invalid login or password")
        response = await self._issue_token_pair(user)
        await self.session.commit()
        return response

    async def refresh(self, raw_token: str) -> TokenResponse:
        payload = self._decode_refresh(raw_token)
        stored_token = await self.tokens.get_active(payload.jti)
        if stored_token is None or stored_token.user_id != payload.subject:
            raise AppError(401, "INVALID_REFRESH_TOKEN", "Refresh token is invalid or expired")

        user = await self.users.get_by_id(payload.subject)
        if user is None:
            raise AppError(401, "INVALID_REFRESH_TOKEN", "Refresh token is invalid or expired")

        await self.tokens.revoke(stored_token)
        response = await self._issue_token_pair(user)
        await self.session.commit()
        return response

    async def logout(self, raw_token: str) -> None:
        payload = self._decode_refresh(raw_token)
        stored_token = await self.tokens.get_active(payload.jti)
        if stored_token is not None and stored_token.user_id == payload.subject:
            await self.tokens.revoke(stored_token)
            await self.session.commit()

    async def _issue_token_pair(self, user: User) -> TokenResponse:
        access_token = create_access_token(user.id)
        refresh_token, jti, expires_at = create_refresh_token(user.id)
        self.tokens.add(
            RefreshToken(jti=jti, user_id=user.id, expires_at=expires_at)
        )
        await self.session.flush()
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user,
        )

    @staticmethod
    def _decode_refresh(raw_token: str):  # type: ignore[no-untyped-def]
        try:
            return decode_token(raw_token, "refresh")
        except InvalidTokenError as exc:
            raise AppError(
                401, "INVALID_REFRESH_TOKEN", "Refresh token is invalid or expired"
            ) from exc

