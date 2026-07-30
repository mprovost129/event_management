from unittest.mock import patch

import pytest
import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from workspace.file_scanning import (
    MalwareDetected,
    MalwareScannerUnavailable,
    scan_upload,
)


class FakeClamAVConnection:
    def __init__(self, response):
        self.response = response
        self.sent = bytearray()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def sendall(self, data):
        self.sent.extend(data)

    def recv(self, size):
        response, self.response = self.response, b""
        return response


class FakeCloudmersiveResponse:
    def __init__(self, result, status_error=None, status_code=200):
        self.result = result
        self.status_error = status_error
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_error:
            raise self.status_error

    def json(self):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@override_settings(DOCUMENT_UPLOAD_SCAN_BACKEND="clamav")
def test_clamav_streams_upload_bytes_and_restores_the_file_position():
    connection = FakeClamAVConnection(b"stream: OK\0")
    upload = SimpleUploadedFile("notes.txt", b"safe document")

    with patch(
        "workspace.file_scanning.socket.create_connection",
        return_value=connection,
    ):
        scan_upload(upload)

    assert connection.sent.startswith(b"zINSTREAM\0")
    assert b"safe document" in connection.sent
    assert connection.sent.endswith(b"\0\0\0\0")
    assert upload.tell() == 0


@override_settings(DOCUMENT_UPLOAD_SCAN_BACKEND="clamav")
def test_clamav_detection_and_outage_fail_closed():
    infected = SimpleUploadedFile("infected.txt", b"unsafe document")
    connection = FakeClamAVConnection(b"stream: Test.Signature FOUND\0")
    with patch(
        "workspace.file_scanning.socket.create_connection",
        return_value=connection,
    ):
        with pytest.raises(MalwareDetected):
            scan_upload(infected)

    unavailable = SimpleUploadedFile("unavailable.txt", b"document")
    with patch(
        "workspace.file_scanning.socket.create_connection",
        side_effect=OSError("scanner offline"),
    ):
        with pytest.raises(MalwareScannerUnavailable):
            scan_upload(unavailable)

    assert infected.tell() == 0
    assert unavailable.tell() == 0


@override_settings(
    DOCUMENT_UPLOAD_SCAN_BACKEND="cloudmersive",
    CLOUDMERSIVE_API_KEY="test-api-key",
    CLOUDMERSIVE_API_URL="https://api.cloudmersive.test/virus/scan/file/advanced",
    CLOUDMERSIVE_TIMEOUT_SECONDS=20,
    DOCUMENT_UPLOAD_ALLOWED_EXTENSIONS=("pdf", "docx"),
)
def test_cloudmersive_scans_upload_with_restrictive_policy_and_restores_position():
    upload = SimpleUploadedFile(
        "minutes.pdf",
        b"safe document",
        content_type="application/pdf",
    )

    with patch(
        "workspace.file_scanning.requests.post",
        return_value=FakeCloudmersiveResponse({"CleanResult": True}),
    ) as post:
        scan_upload(upload)

    assert upload.tell() == 0
    _, kwargs = post.call_args
    assert kwargs["headers"]["Apikey"] == "test-api-key"
    assert kwargs["headers"]["allowMacros"] == "false"
    assert kwargs["headers"]["allowPasswordProtectedFiles"] == "false"
    assert kwargs["headers"]["restrictFileTypes"] == ".pdf,.docx"
    assert kwargs["files"]["inputFile"] == (
        "minutes.pdf",
        upload,
        "application/pdf",
    )
    assert kwargs["timeout"] == 20
    assert kwargs["allow_redirects"] is False


@override_settings(
    DOCUMENT_UPLOAD_SCAN_BACKEND="cloudmersive",
    CLOUDMERSIVE_API_KEY="test-api-key",
)
def test_cloudmersive_detection_and_outage_fail_closed():
    rejected = SimpleUploadedFile("rejected.pdf", b"unsafe document")
    with patch(
        "workspace.file_scanning.requests.post",
        return_value=FakeCloudmersiveResponse({"CleanResult": False}),
    ):
        with pytest.raises(MalwareDetected):
            scan_upload(rejected)

    unavailable = SimpleUploadedFile("unavailable.pdf", b"document")
    with patch(
        "workspace.file_scanning.requests.post",
        side_effect=requests.Timeout("scanner offline"),
    ):
        with pytest.raises(MalwareScannerUnavailable):
            scan_upload(unavailable)

    unexpected = SimpleUploadedFile("unexpected.pdf", b"document")
    with patch(
        "workspace.file_scanning.requests.post",
        return_value=FakeCloudmersiveResponse([{"CleanResult": True}]),
    ):
        with pytest.raises(MalwareScannerUnavailable):
            scan_upload(unexpected)

    assert rejected.tell() == 0
    assert unavailable.tell() == 0
    assert unexpected.tell() == 0


@override_settings(
    DOCUMENT_UPLOAD_SCAN_BACKEND="cloudmersive",
    CLOUDMERSIVE_API_KEY="",
)
def test_cloudmersive_missing_api_key_fails_closed_without_calling_api():
    upload = SimpleUploadedFile("document.pdf", b"document")

    with patch("workspace.file_scanning.requests.post") as post:
        with pytest.raises(MalwareScannerUnavailable):
            scan_upload(upload)

    post.assert_not_called()
