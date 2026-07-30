import socket
import struct

from django.conf import settings
from django.core.exceptions import ValidationError


class MalwareDetected(ValidationError):
    pass


class MalwareScannerUnavailable(ValidationError):
    pass


def _clamav_response(connection):
    response = bytearray()
    while len(response) < 4096:
        chunk = connection.recv(4096)
        if not chunk:
            break
        response.extend(chunk)
        if b"\0" in chunk:
            break
    return bytes(response).rstrip(b"\0").decode("utf-8", errors="replace")


def _scan_with_clamav(upload):
    try:
        upload.seek(0)
        with socket.create_connection(
            (settings.CLAMAV_HOST, settings.CLAMAV_PORT),
            timeout=settings.CLAMAV_TIMEOUT_SECONDS,
        ) as connection:
            connection.sendall(b"zINSTREAM\0")
            for chunk in upload.chunks(chunk_size=64 * 1024):
                connection.sendall(struct.pack("!I", len(chunk)))
                connection.sendall(chunk)
            connection.sendall(struct.pack("!I", 0))
            response = _clamav_response(connection)
    except (OSError, ValueError) as exc:
        raise MalwareScannerUnavailable(
            "The security scanner is temporarily unavailable. Try the upload again."
        ) from exc
    finally:
        upload.seek(0)

    if response.endswith("OK"):
        return
    if response.endswith("FOUND"):
        raise MalwareDetected(
            "This file was rejected because the security scanner detected malware."
        )
    raise MalwareScannerUnavailable(
        "The security scanner returned an unexpected response. Try the upload again."
    )


def scan_upload(upload):
    backend = settings.DOCUMENT_UPLOAD_SCAN_BACKEND
    if backend == "disabled":
        return
    if backend == "clamav":
        _scan_with_clamav(upload)
        return
    raise MalwareScannerUnavailable("The configured security scanner is not supported.")
