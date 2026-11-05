from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AttachmentReserveRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=120)
    file_size: int = Field(gt=0)

    @field_validator("filename")
    @classmethod
    def normalize_filename(cls, value: str) -> str:
        normalized = value.strip().replace("\\", "/").split("/")[-1]
        if not normalized or normalized in {".", ".."}:
            raise ValueError("Filename is invalid")
        return normalized

    @field_validator("mime_type")
    @classmethod
    def normalize_mime_type(cls, value: str) -> str:
        return value.strip().lower()


class AttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    mime_type: str
    file_size: int
    uploaded_at: Optional[datetime]
    download_url: str


class AttachmentUploadResponse(BaseModel):
    attachment: AttachmentResponse
    upload_url: str
    upload_headers: dict[str, str]
    expires_at: datetime
