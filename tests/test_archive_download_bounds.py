"""One Internet Archive response cannot consume unbounded process memory."""

from __future__ import annotations

import io

import pytest

import concordance.archive as archive


class _Response:
    def __init__(self, body: bytes, content_length: str | None = None) -> None:
        self._body = io.BytesIO(body)
        self.headers = {} if content_length is None else {
            "Content-Length": content_length,
        }

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)


def test_declared_oversize_archive_response_is_rejected_before_read(monkeypatch) -> None:
    response = _Response(b"unused", "11")
    monkeypatch.setattr(archive.urllib.request, "urlopen", lambda *a, **k: response)

    with pytest.raises(archive.ArchiveError, match="exceeds 10 bytes"):
        archive._get("https://archive.test/item", max_bytes=10, retries=1)

    assert response._body.tell() == 0


def test_streamed_oversize_archive_response_is_bounded(monkeypatch) -> None:
    response = _Response(b"01234567890")
    monkeypatch.setattr(archive.urllib.request, "urlopen", lambda *a, **k: response)

    with pytest.raises(archive.ArchiveError, match="exceeds 10 bytes"):
        archive._get("https://archive.test/item", max_bytes=10, retries=1)

    assert response._body.tell() == 11


def test_in_budget_archive_response_is_returned(monkeypatch) -> None:
    response = _Response(b"0123456789", "10")
    monkeypatch.setattr(archive.urllib.request, "urlopen", lambda *a, **k: response)

    assert archive._get(
        "https://archive.test/item", max_bytes=10, retries=1,
    ) == b"0123456789"
