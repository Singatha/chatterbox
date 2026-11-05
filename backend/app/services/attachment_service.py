from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.storage import ObjectStorage
from app.models.attachment import Attachment
from app.repositories.attachment_repository import AttachmentRepository
from app.schemas.attachment import AttachmentResponse, AttachmentUploadResponse
from app.services.conversation_service import ConversationService

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/zip",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
    "text/plain",
}


class AttachmentService:
    def __init__(self, session: AsyncSession, storage: ObjectStorage) -> None:
        self.session = session
        self.storage = storage
        self.attachments = AttachmentRepository(session)
        self.conversations = ConversationService(session)

    async def reserve(
        self,
        conversation_id: UUID,
        uploader_id: UUID,
        filename: str,
        mime_type: str,
        file_size: int,
    ) -> AttachmentUploadResponse:
        await self.conversations.get_authorized(conversation_id, uploader_id)
        self._validate_metadata(mime_type, file_size)
        attachment_id = uuid4()
        suffix = Path(filename).suffix.lower()[:16]
        storage_key = f"{conversation_id}/{uploader_id}/{attachment_id}{suffix}"
        attachment = Attachment(
            id=attachment_id,
            conversation_id=conversation_id,
            uploader_id=uploader_id,
            filename=filename,
            mime_type=mime_type,
            file_size=file_size,
            storage_key=storage_key,
        )
        self.attachments.add(attachment)
        expires = timedelta(minutes=settings.attachment_upload_expire_minutes)
        upload_url = await self.storage.presigned_put(storage_key, expires)
        await self.session.commit()
        return AttachmentUploadResponse(
            attachment=self.to_response(attachment),
            upload_url=upload_url,
            upload_headers={"Content-Type": mime_type},
            expires_at=datetime.now(timezone.utc) + expires,
        )

    async def complete(self, attachment_id: UUID, current_user_id: UUID) -> AttachmentResponse:
        attachment = await self.attachments.get_by_id_for_update(attachment_id)
        if attachment is None or attachment.uploader_id != current_user_id:
            raise AppError(404, "ATTACHMENT_NOT_FOUND", "Attachment was not found")
        await self.conversations.get_authorized(
            attachment.conversation_id, current_user_id
        )
        if attachment.uploaded_at is not None:
            return self.to_response(attachment)
        metadata = await self.storage.stat(attachment.storage_key)
        if metadata is None:
            raise AppError(409, "ATTACHMENT_NOT_UPLOADED", "Upload has not completed")
        actual_mime_type = metadata.content_type.split(";", 1)[0].strip().lower()
        if metadata.size != attachment.file_size:
            raise AppError(422, "ATTACHMENT_SIZE_MISMATCH", "Uploaded file size is invalid")
        if actual_mime_type != attachment.mime_type:
            raise AppError(422, "ATTACHMENT_TYPE_MISMATCH", "Uploaded file type is invalid")
        attachment.uploaded_at = datetime.now(timezone.utc)
        await self.session.commit()
        return self.to_response(attachment)

    async def authorize_download(
        self, attachment_id: UUID, current_user_id: UUID
    ) -> Attachment:
        attachment = await self.attachments.get_by_id(attachment_id)
        if (
            attachment is None
            or attachment.message_id is None
            or attachment.uploaded_at is None
        ):
            raise AppError(404, "ATTACHMENT_NOT_FOUND", "Attachment was not found")
        await self.conversations.get_authorized(
            attachment.conversation_id, current_user_id
        )
        return attachment

    async def cleanup_abandoned(self, cutoff: datetime, limit: int = 100) -> int:
        abandoned = await self.attachments.list_abandoned(cutoff, limit)
        removed = 0
        for attachment in abandoned:
            try:
                await self.storage.remove(attachment.storage_key)
            except Exception:
                continue
            await self.attachments.delete(attachment)
            removed += 1
        await self.session.commit()
        return removed

    @staticmethod
    def to_response(attachment: Attachment) -> AttachmentResponse:
        return AttachmentResponse(
            id=attachment.id,
            filename=attachment.filename,
            mime_type=attachment.mime_type,
            file_size=attachment.file_size,
            uploaded_at=attachment.uploaded_at,
            download_url=f"/attachments/{attachment.id}/download",
        )

    @staticmethod
    def _validate_metadata(mime_type: str, file_size: int) -> None:
        if mime_type not in ALLOWED_MIME_TYPES:
            raise AppError(422, "ATTACHMENT_TYPE_NOT_ALLOWED", "File type is not allowed")
        if file_size > settings.attachment_max_bytes:
            raise AppError(422, "ATTACHMENT_TOO_LARGE", "File exceeds the upload limit")
