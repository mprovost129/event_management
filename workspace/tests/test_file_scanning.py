from unittest.mock import patch

import pytest
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
