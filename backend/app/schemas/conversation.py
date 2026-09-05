from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DirectConversationCreate(BaseModel):
    participant_id: UUID


class ConversationMemberResponse(BaseModel):
    user_id: UUID
    username: str
    role: str
    last_seen: Optional[datetime]


class MessageSummary(BaseModel):
    id: UUID
    sender_id: UUID
    sender_username: str
    content: str
    created_at: datetime


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: Literal["direct"]
    name: Optional[str]
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    members: list[ConversationMemberResponse]
    last_message: Optional[MessageSummary] = None
    unread_count: int = 0
