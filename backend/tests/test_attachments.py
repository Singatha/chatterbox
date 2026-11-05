from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import StoredObjectMetadata, get_object_storage
from app.main import app
from app.models.attachment import Attachment
from app.services.attachment_service import AttachmentService
from tests.test_direct_messaging import auth_headers, create_direct, register_user


class FakeDownload:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.closed = False

    def stream(self, amt: int):  # type: ignore[no-untyped-def]
        for offset in range(0, len(self.content), amt):
            yield self.content[offset : offset + amt]

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        pass


class FakeStorage:
    def __init__(self) -> None:
        self.last_key = ""
        self.objects: dict[str, tuple[StoredObjectMetadata, bytes]] = {}
        self.removed: list[str] = []

    async def presigned_put(self, storage_key: str, expires) -> str:  # type: ignore[no-untyped-def]
        self.last_key = storage_key
        return f"http://uploads.test/{storage_key}"

    async def stat(self, storage_key: str):  # type: ignore[no-untyped-def]
        stored = self.objects.get(storage_key)
        return stored[0] if stored else None

    async def get(self, storage_key: str) -> FakeDownload:
        return FakeDownload(self.objects[storage_key][1])

    async def remove(self, storage_key: str) -> None:
        self.objects.pop(storage_key, None)
        self.removed.append(storage_key)


async def test_attachment_upload_message_and_authorized_download(client) -> None:
    storage = FakeStorage()
    app.dependency_overrides[get_object_storage] = lambda: storage
    alice = await register_user(client, "alice")
    bob = await register_user(client, "bob")
    mallory = await register_user(client, "mallory")
    conversation = await create_direct(client, alice, bob)
    content = b"attachment contents"

    invalid = await client.post(
        f"/conversations/{conversation['id']}/attachments",
        headers=auth_headers(alice),
        json={
            "filename": "malware.exe",
            "mime_type": "application/x-msdownload",
            "file_size": 100,
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "ATTACHMENT_TYPE_NOT_ALLOWED"

    reserved = await client.post(
        f"/conversations/{conversation['id']}/attachments",
        headers=auth_headers(alice),
        json={
            "filename": "../notes.txt",
            "mime_type": "text/plain",
            "file_size": len(content),
        },
    )
    assert reserved.status_code == 201
    reservation = reserved.json()
    attachment_id = reservation["attachment"]["id"]
    assert reservation["attachment"]["filename"] == "notes.txt"
    assert reservation["upload_url"].startswith("http://uploads.test/")
    storage.objects[storage.last_key] = (
        StoredObjectMetadata(size=len(content), content_type="text/plain"),
        content,
    )

    completed = await client.post(
        f"/attachments/{attachment_id}/complete",
        headers=auth_headers(alice),
    )
    assert completed.status_code == 200
    assert completed.json()["uploaded_at"] is not None

    sent = await client.post(
        f"/conversations/{conversation['id']}/messages",
        headers=auth_headers(alice),
        json={"content": "", "attachment_ids": [attachment_id]},
    )
    assert sent.status_code == 201
    assert sent.json()["content"] == ""
    assert sent.json()["attachments"][0]["filename"] == "notes.txt"

    downloaded = await client.get(
        f"/attachments/{attachment_id}/download",
        headers=auth_headers(bob),
    )
    assert downloaded.status_code == 200
    assert downloaded.content == content
    assert downloaded.headers["content-type"] == "text/plain; charset=utf-8"

    forbidden = await client.get(
        f"/attachments/{attachment_id}/download",
        headers=auth_headers(mallory),
    )
    assert forbidden.status_code == 403

    reused = await client.post(
        f"/conversations/{conversation['id']}/messages",
        headers=auth_headers(alice),
        json={"content": "reuse", "attachment_ids": [attachment_id]},
    )
    assert reused.status_code == 422
    assert reused.json()["error"]["code"] == "INVALID_ATTACHMENTS"


async def test_attachment_completion_rejects_tampered_object(client) -> None:
    storage = FakeStorage()
    app.dependency_overrides[get_object_storage] = lambda: storage
    alice = await register_user(client, "alice")
    bob = await register_user(client, "bob")
    conversation = await create_direct(client, alice, bob)
    reserved = await client.post(
        f"/conversations/{conversation['id']}/attachments",
        headers=auth_headers(alice),
        json={"filename": "photo.png", "mime_type": "image/png", "file_size": 20},
    )
    attachment_id = reserved.json()["attachment"]["id"]
    storage.objects[storage.last_key] = (
        StoredObjectMetadata(size=21, content_type="image/png"),
        b"x" * 21,
    )

    completed = await client.post(
        f"/attachments/{attachment_id}/complete", headers=auth_headers(alice)
    )

    assert completed.status_code == 422
    assert completed.json()["error"]["code"] == "ATTACHMENT_SIZE_MISMATCH"


async def test_abandoned_attachment_cleanup(
    client,
    session: AsyncSession,
) -> None:
    storage = FakeStorage()
    app.dependency_overrides[get_object_storage] = lambda: storage
    alice = await register_user(client, "alice")
    bob = await register_user(client, "bob")
    conversation = await create_direct(client, alice, bob)
    reserved = await client.post(
        f"/conversations/{conversation['id']}/attachments",
        headers=auth_headers(alice),
        json={"filename": "old.txt", "mime_type": "text/plain", "file_size": 3},
    )
    attachment_id = UUID(reserved.json()["attachment"]["id"])
    attachment = await session.get(Attachment, attachment_id)
    assert attachment is not None
    attachment.created_at = datetime.now(timezone.utc) - timedelta(days=2)
    await session.commit()

    removed = await AttachmentService(session, storage).cleanup_abandoned(
        datetime.now(timezone.utc) - timedelta(days=1)
    )

    assert removed == 1
    assert storage.removed == [attachment.storage_key]
    assert await session.get(Attachment, attachment_id) is None
