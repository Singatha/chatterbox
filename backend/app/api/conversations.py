from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.dependencies import CurrentUser, DbSession
from app.schemas.conversation import ConversationResponse, DirectConversationCreate
from app.schemas.message import MessageCreate, MessagePage, MessageResponse
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    data: DirectConversationCreate, session: DbSession, current_user: CurrentUser
) -> ConversationResponse:
    return await ConversationService(session).create_direct(
        current_user.id, data.participant_id
    )


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    session: DbSession, current_user: CurrentUser
) -> list[ConversationResponse]:
    return await ConversationService(session).list(current_user.id)


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID, session: DbSession, current_user: CurrentUser
) -> ConversationResponse:
    return await ConversationService(session).get(conversation_id, current_user.id)


@router.get("/{conversation_id}/messages", response_model=MessagePage)
async def list_messages(
    conversation_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before: Annotated[Optional[str], Query(max_length=512)] = None,
) -> MessagePage:
    return await MessageService(session).list(
        conversation_id, current_user.id, limit, before
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    conversation_id: UUID,
    data: MessageCreate,
    session: DbSession,
    current_user: CurrentUser,
) -> MessageResponse:
    return await MessageService(session).create(
        conversation_id, current_user.id, data.content
    )

