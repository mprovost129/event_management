import socket
import struct

import requests
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


def _scan_with_cloudmersive(upload):
    api_key = settings.CLOUDMERSIVE_API_KEY
    if not api_key:
        raise MalwareScannerUnavailable(
            "The security scanner is not configured. Contact support."
        )

    filename = getattr(upload, "name", "upload") or "upload"
    content_type = getattr(upload, "content_type", None) or "application/octet-stream"
    allowed_extensions = ",".join(
        f".{extension}" for extension in settings.DOCUMENT_UPLOAD_ALLOWED_EXTENSIONS
    )
    headers = {
        "Apikey": api_key,
        "fileName": filename,
        "allowExecutables": "false",
        "allowInvalidFiles": "false",
        "allowScripts": "false",
        "allowPasswordProtectedFiles": "false",
        "allowMacros": "false",
        "allowXmlExternalEntities": "false",
        "allowInsecureDeserialization": "false",
        "allowHtml": "false",
        "allowUnsafeArchives": "false",
        "allowOleEmbeddedObject": "false",
        "allowUnwantedAction": "false",
        "restrictFileTypes": allowed_extensions,
    }

    try:
        upload.seek(0)
        response = requests.post(
            settings.CLOUDMERSIVE_API_URL,
            headers=headers,
            files={"inputFile": (filename, upload, content_type)},
            timeout=settings.CLOUDMERSIVE_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
        response.raise_for_status()
        if not 200 <= response.status_code < 300:
            raise MalwareScannerUnavailable(
                "The security scanner returned an unexpected response. "
                "Try the upload again."
            )
        result = response.json()
    except (requests.RequestException, TypeError, ValueError):
        raise MalwareScannerUnavailable(
            "The security scanner is temporarily unavailable. Try the upload again."
        ) from None
    finally:
        upload.seek(0)

    if not isinstance(result, dict):
        raise MalwareScannerUnavailable(
            "The security scanner returned an unexpected response. Try the upload again."
        )
    if result.get("CleanResult") is True:
        return
    if result.get("CleanResult") is False:
        raise MalwareDetected(
            "This file was rejected because it did not pass the security scan."
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
    if backend == "cloudmersive":
        _scan_with_cloudmersive(upload)
        return
    raise MalwareScannerUnavailable("The configured security scanner is not supported.")
