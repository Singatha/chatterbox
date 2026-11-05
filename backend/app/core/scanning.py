import socket
import struct
from typing import Any, Protocol

from anyio import to_thread

from app.core.config import settings
from app.core.errors import AppError
from app.core.observability import ATTACHMENT_SCANS_TOTAL
from app.core.storage import ObjectStorage


class AttachmentScanner(Protocol):
    name: str

    async def scan(self, storage: ObjectStorage, storage_key: str) -> None: ...


class DisabledAttachmentScanner:
    name = "disabled"

    async def scan(self, storage: ObjectStorage, storage_key: str) -> None:
        del storage, storage_key
        ATTACHMENT_SCANS_TOTAL.labels(scanner=self.name, outcome="skipped").inc()


class ClamAVAttachmentScanner:
    name = "clamav"

    async def scan(self, storage: ObjectStorage, storage_key: str) -> None:
        response = await storage.get(storage_key)
        try:
            result = await to_thread.run_sync(self._scan_response, response)
        except (OSError, TimeoutError) as exc:
            ATTACHMENT_SCANS_TOTAL.labels(
                scanner=self.name, outcome="unavailable"
            ).inc()
            raise AppError(
                503,
                "ATTACHMENT_SCAN_UNAVAILABLE",
                "Attachment scanning is temporarily unavailable",
            ) from exc
        if result.endswith("FOUND"):
            ATTACHMENT_SCANS_TOTAL.labels(scanner=self.name, outcome="infected").inc()
            raise AppError(
                422,
                "ATTACHMENT_INFECTED",
                "The uploaded file did not pass the security scan",
            )
        if not result.endswith("OK"):
            ATTACHMENT_SCANS_TOTAL.labels(scanner=self.name, outcome="error").inc()
            raise AppError(
                503,
                "ATTACHMENT_SCAN_UNAVAILABLE",
                "Attachment scanning returned an invalid result",
            )
        ATTACHMENT_SCANS_TOTAL.labels(scanner=self.name, outcome="clean").inc()

    @staticmethod
    def _scan_response(response: Any) -> str:
        try:
            with socket.create_connection(
                (settings.clamav_host, settings.clamav_port),
                timeout=settings.clamav_timeout_seconds,
            ) as connection:
                connection.settimeout(settings.clamav_timeout_seconds)
                connection.sendall(b"zINSTREAM\0")
                for chunk in response.stream(amt=64 * 1024):
                    connection.sendall(struct.pack("!I", len(chunk)))
                    connection.sendall(chunk)
                connection.sendall(struct.pack("!I", 0))
                result = bytearray()
                while len(result) < 4096:
                    part = connection.recv(4096 - len(result))
                    if not part:
                        break
                    result.extend(part)
                    if b"\0" in part:
                        break
                return result.rstrip(b"\0").decode("utf-8", errors="replace")
        finally:
            response.close()
            response.release_conn()


attachment_scanner: AttachmentScanner
if settings.attachment_scan_mode == "clamav":
    attachment_scanner = ClamAVAttachmentScanner()
else:
    attachment_scanner = DisabledAttachmentScanner()


def get_attachment_scanner() -> AttachmentScanner:
    return attachment_scanner
