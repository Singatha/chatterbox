from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.conversation import Conversation
from app.models.conversation_member import ConversationMember
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.user_repository import UserRepository
from app.schemas.conversation import (
    ConversationMemberResponse,
    ConversationResponse,
    MessageSummary,
)


def direct_key(first_user_id: UUID, second_user_id: UUID) -> str:
    return ":".join(sorted((str(first_user_id), str(second_user_id))))


class ConversationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.conversations = ConversationRepository(session)
        self.messages = MessageRepository(session)
        self.users = UserRepository(session)

    async def create_direct(
        self, current_user_id: UUID, participant_id: UUID
    ) -> ConversationResponse:
        if current_user_id == participant_id:
            raise AppError(422, "INVALID_PARTICIPANT", "You cannot message yourself")
        if await self.users.get_by_id(participant_id) is None:
            raise AppError(404, "USER_NOT_FOUND", "User was not found")

        key = direct_key(current_user_id, participant_id)
        existing = await self.conversations.get_direct_by_key(key)
        if existing is not None:
            return await self._to_response(existing, current_user_id)

        conversation = Conversation(type="direct", direct_key=key, created_by=current_user_id)
        conversation.members = [
            ConversationMember(user_id=current_user_id, role="member"),
            ConversationMember(user_id=participant_id, role="member"),
        ]
        self.conversations.add(conversation)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.conversations.get_direct_by_key(key)
            if existing is None:
                raise
            return await self._to_response(existing, current_user_id)
        created = await self.conversations.get_by_id(conversation.id)
        if created is None:  # pragma: no cover - defensive invariant
            raise AppError(500, "CONVERSATION_CREATE_FAILED", "Conversation could not be created")
        return await self._to_response(created, current_user_id)

    async def list(self, current_user_id: UUID) -> list[ConversationResponse]:
        conversations = await self.conversations.list_for_user(current_user_id)
        return [await self._to_response(item, current_user_id) for item in conversations]

    async def get_authorized(
        self, conversation_id: UUID, current_user_id: UUID
    ) -> Conversation:
        conversation = await self.conversations.get_by_id(conversation_id)
        if conversation is None:
            raise AppError(404, "CONVERSATION_NOT_FOUND", "Conversation was not found")
        if not await self.conversations.is_member(conversation_id, current_user_id):
            raise AppError(403, "CONVERSATION_ACCESS_DENIED", "You are not a conversation member")
        return conversation

    async def get(self, conversation_id: UUID, current_user_id: UUID) -> ConversationResponse:
        return await self._to_response(
            await self.get_authorized(conversation_id, current_user_id), current_user_id
        )

    async def touch(self, conversation: Conversation) -> None:
        conversation.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def _to_response(
        self, conversation: Conversation, current_user_id: UUID
    ) -> ConversationResponse:
        latest = await self.messages.get_latest(conversation.id)
        summary = None
        if latest is not None:
            summary = MessageSummary(
                id=latest.id,
                sender_id=latest.sender_id,
                sender_username=latest.sender.username,
                content=latest.content,
                created_at=latest.created_at,
            )
        return ConversationResponse(
            id=conversation.id,
            type="direct",
            name=conversation.name,
            created_by=conversation.created_by,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            members=[
                ConversationMemberResponse(
                    user_id=member.user_id,
                    username=member.user.username,
                    role=member.role,
                    last_seen=member.user.last_seen,
                )
                for member in conversation.members
            ],
            last_message=summary,
            unread_count=await self.conversations.unread_count(
                conversation.id, current_user_id
            ),
        )
