from collections.abc import Iterator
from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import CurrentUser, DbSession
from app.core.scanning import AttachmentScanner, get_attachment_scanner
from app.core.storage import ObjectStorage, get_object_storage
from app.schemas.attachment import (
    AttachmentReserveRequest,
    AttachmentResponse,
    AttachmentUploadResponse,
)
from app.services.attachment_service import AttachmentService

router = APIRouter(tags=["attachments"])
Storage = Annotated[ObjectStorage, Depends(get_object_storage)]
Scanner = Annotated[AttachmentScanner, Depends(get_attachment_scanner)]


@router.post(
    "/conversations/{conversation_id}/attachments",
    response_model=AttachmentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def reserve_attachment(
    conversation_id: UUID,
    data: AttachmentReserveRequest,
    session: DbSession,
    current_user: CurrentUser,
    storage: Storage,
) -> AttachmentUploadResponse:
    return await AttachmentService(session, storage).reserve(
        conversation_id,
        current_user.id,
        data.filename,
        data.mime_type,
        data.file_size,
    )


@router.post(
    "/attachments/{attachment_id}/complete",
    response_model=AttachmentResponse,
)
async def complete_attachment(
    attachment_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
    storage: Storage,
    scanner: Scanner,
) -> AttachmentResponse:
    return await AttachmentService(session, storage, scanner).complete(
        attachment_id, current_user.id
    )


def stream_object(response: Any) -> Iterator[bytes]:
    try:
        yield from response.stream(amt=64 * 1024)
    finally:
        response.close()
        response.release_conn()


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: UUID,
    session: DbSession,
    current_user: CurrentUser,
    storage: Storage,
) -> StreamingResponse:
    attachment = await AttachmentService(session, storage).authorize_download(
        attachment_id, current_user.id
    )
    response = await storage.get(attachment.storage_key)
    encoded_filename = quote(attachment.filename)
    disposition = "inline" if attachment.mime_type.startswith("image/") else "attachment"
    return StreamingResponse(
        stream_object(response),
        media_type=attachment.mime_type,
        headers={
            "Content-Length": str(attachment.file_size),
            "Content-Disposition": (
                f"{disposition}; filename*=UTF-8''{encoded_filename}"
            ),
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )
