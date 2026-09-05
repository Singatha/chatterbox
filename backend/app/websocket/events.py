from typing import Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field, TypeAdapter, field_validator

from app.schemas.message import MessageResponse


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


ClientEvent = Union[MessageSendEvent]
client_event_adapter = TypeAdapter(ClientEvent)


class ConnectionReadyEvent(BaseModel):
    type: Literal["connection.ready"] = "connection.ready"
    data: dict[str, str]


class MessageCreatedEvent(BaseModel):
    type: Literal["message.created"] = "message.created"
    request_id: Optional[str] = None
    data: MessageResponse


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    request_id: Optional[str] = None
    error: ErrorDetail
