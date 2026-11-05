from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.attachment import AttachmentResponse


class MessageCreate(BaseModel):
    content: str = Field(default="", max_length=4000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def require_content_or_attachment(self) -> "MessageCreate":
        self.content = self.content.strip()
        if not self.content and not self.attachment_ids:
            raise ValueError("Message must contain text or an attachment")
        if len(set(self.attachment_ids)) != len(self.attachment_ids):
            raise ValueError("Attachment IDs must be unique")
        return self


class MessageReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    delivered_at: Optional[datetime]
    read_at: Optional[datetime]


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    sender_id: UUID
    sender_username: str
    content: str
    created_at: datetime
    edited_at: Optional[datetime]
    cursor: str
    receipts: list[MessageReceiptResponse]
    attachments: list[AttachmentResponse]


class MessagePage(BaseModel):
    items: list[MessageResponse]
    next_cursor: Optional[str]
