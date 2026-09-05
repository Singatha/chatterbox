from typing import Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field, TypeAdapter, field_validator

from app.schemas.message import MessageResponse
from app.schemas.receipt import ReceiptEventData


class MessageSendEvent(BaseModel):
    type: Literal["message.send"]
    request_id: Optional[str] = Field(default=None, max_length=64)
    conversation_id: UUID
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be blank")
        return value


class MessageReadRequest(BaseModel):
    type: Literal["message.read"]
    request_id: Optional[str] = Field(default=None, max_length=64)
    conversation_id: UUID
    message_id: UUID


class TypingStartEvent(BaseModel):
    type: Literal["typing.start"]
    conversation_id: UUID


class TypingStopEvent(BaseModel):
    type: Literal["typing.stop"]
    conversation_id: UUID


ClientEvent = Union[MessageSendEvent, MessageReadRequest, TypingStartEvent, TypingStopEvent]
client_event_adapter = TypeAdapter(ClientEvent)


class ConnectionReadyData(BaseModel):
    user_id: UUID
    online_user_ids: list[UUID]


class ConnectionReadyEvent(BaseModel):
    type: Literal["connection.ready"] = "connection.ready"
    data: ConnectionReadyData


class MessageCreatedEvent(BaseModel):
    type: Literal["message.created"] = "message.created"
    request_id: Optional[str] = None
    data: MessageResponse


class MessageDeliveredEvent(BaseModel):
    type: Literal["message.delivered"] = "message.delivered"
    data: ReceiptEventData


class MessageReadEvent(BaseModel):
    type: Literal["message.read"] = "message.read"
    request_id: Optional[str] = None
    data: ReceiptEventData


class TypingEventData(BaseModel):
    conversation_id: UUID
    user_id: UUID


class TypingStartedEvent(BaseModel):
    type: Literal["typing.start"] = "typing.start"
    data: TypingEventData


class TypingStoppedEvent(BaseModel):
    type: Literal["typing.stop"] = "typing.stop"
    data: TypingEventData


class PresenceOnlineData(BaseModel):
    user_id: UUID


class PresenceOfflineData(BaseModel):
    user_id: UUID
    last_seen: str


class PresenceOnlineEvent(BaseModel):
    type: Literal["presence.online"] = "presence.online"
    data: PresenceOnlineData


class PresenceOfflineEvent(BaseModel):
    type: Literal["presence.offline"] = "presence.offline"
    data: PresenceOfflineData


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    request_id: Optional[str] = None
    error: ErrorDetail
