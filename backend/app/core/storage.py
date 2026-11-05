from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Optional

from anyio import to_thread
from minio import Minio
from minio.commonconfig import CopySource
from minio.error import S3Error

from app.core.config import settings


@dataclass(frozen=True)
class StoredObjectMetadata:
    size: int
    content_type: str
    etag: str


class ObjectChangedError(Exception):
    pass


class ObjectStorage:
    def __init__(self) -> None:
        credentials = {
            "access_key": settings.minio_access_key,
            "secret_key": settings.minio_secret_key,
        }
        self.bucket = settings.minio_bucket
        self._internal = Minio(
            settings.minio_endpoint,
            secure=settings.minio_secure,
            region=settings.minio_region,
            **credentials,
        )
        self._public = Minio(
            settings.minio_public_endpoint,
            secure=settings.minio_public_secure,
            region=settings.minio_region,
            **credentials,
        )

    async def ensure_bucket(self) -> None:
        exists = await to_thread.run_sync(self._internal.bucket_exists, self.bucket)
        if not exists:
            await to_thread.run_sync(self._internal.make_bucket, self.bucket)

    async def healthcheck(self) -> bool:
        return await to_thread.run_sync(self._internal.bucket_exists, self.bucket)

    async def presigned_put(self, storage_key: str, expires: timedelta) -> str:
        return await to_thread.run_sync(
            self._public.presigned_put_object,
            self.bucket,
            storage_key,
            expires,
        )

    async def stat(self, storage_key: str) -> Optional[StoredObjectMetadata]:
        try:
            result = await to_thread.run_sync(
                self._internal.stat_object, self.bucket, storage_key
            )
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject"}:
                return None
            raise
        return StoredObjectMetadata(
            size=result.size,
            content_type=result.content_type or "application/octet-stream",
            etag=result.etag,
        )

    async def copy_if_unchanged(
        self, source_key: str, destination_key: str, etag: str
    ) -> None:
        source = CopySource(self.bucket, source_key, match_etag=etag)
        try:
            await to_thread.run_sync(
                self._internal.copy_object,
                self.bucket,
                destination_key,
                source,
            )
        except S3Error as exc:
            if exc.code in {"PreconditionFailed", "InvalidRequest"}:
                raise ObjectChangedError from exc
            raise

    async def get(self, storage_key: str) -> Any:
        return await to_thread.run_sync(
            self._internal.get_object, self.bucket, storage_key
        )

    async def remove(self, storage_key: str) -> None:
        await to_thread.run_sync(
            self._internal.remove_object, self.bucket, storage_key
        )


object_storage = ObjectStorage()


def get_object_storage() -> ObjectStorage:
    return object_storage
