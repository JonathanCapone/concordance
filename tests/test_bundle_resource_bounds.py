"""Public bundle verification must have a finite, visible work budget."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest

import concordance.server as server


def _record(identifier: str = "item", page: int = 1) -> dict:
    return {
        "parameter": "BOD",
        "value": 1,
        "provenance": {
            "identifier": identifier,
            "page": page,
            "source_text": "BOD was 1 mg/L.",
        },
    }


def _handler(bundle: dict, *, forwarded_for: str = "") -> server.Handler:
    body = json.dumps(bundle).encode()
    handler = object.__new__(server.Handler)
    handler.path = "/api/bundle"
    handler.client_address = ("192.0.2.44", 4567)
    handler.headers = {
        "Content-Length": str(len(body)),
        "Content-Type": "application/json",
        "Host": "localhost",
    }
    if forwarded_for:
        handler.headers["X-Forwarded-For"] = forwarded_for
    handler.rfile = io.BytesIO(body)
    return handler


def _capture(handler: server.Handler) -> dict:
    sent: dict = {}
    handler._send = lambda payload, ctype, **kwargs: sent.update(
        body=json.loads(payload), ctype=ctype, **kwargs,
    )
    return sent


class _MustNotRun:
    def check(self, peer: str) -> tuple[bool, int]:
        raise AssertionError("resource rejection must precede the rate limiter")


@pytest.mark.parametrize(
    ("records", "reason"),
    [
        ([{}] * (server.MAX_BUNDLE_RECORDS + 1), "records; maximum"),
        (
            [_record(f"item-{n}") for n in range(server.MAX_BUNDLE_IDENTIFIERS + 1)],
            "unique identifiers",
        ),
        (
            [_record("one-item", n + 1) for n in range(server.MAX_BUNDLE_PAGES + 1)],
            "identifier/page pairs",
        ),
    ],
)
def test_resource_caps_reject_before_archive_verification(
    monkeypatch, records: list[dict], reason: str,
) -> None:
    def verification_must_not_run(*args, **kwargs):
        raise AssertionError("over-budget bundles must not reach the archive")

    handler = _handler({"records": records})
    sent = _capture(handler)
    monkeypatch.setattr(server, "STATE", SimpleNamespace(archive=object()))
    monkeypatch.setattr(server, "BUNDLE_RATE_LIMITER", _MustNotRun())
    monkeypatch.setattr(server, "verify_bundle", verification_must_not_run)

    handler.do_POST()

    assert sent["status"] == 413
    assert reason in sent["body"]["why"]
    assert sent["body"]["limits"] == {
        "records": server.MAX_BUNDLE_RECORDS,
        "identifiers": server.MAX_BUNDLE_IDENTIFIERS,
        "identifier_pages": server.MAX_BUNDLE_PAGES,
    }


def test_busy_verifier_returns_nonblocking_503(monkeypatch) -> None:
    class Allow:
        def check(self, peer: str) -> tuple[bool, int]:
            return True, 0

    class Busy:
        def acquire(self, *, blocking: bool) -> bool:
            assert blocking is False
            return False

        def release(self) -> None:
            raise AssertionError("a slot that was not acquired must not be released")

    def verification_must_not_run(*args, **kwargs):
        raise AssertionError("busy requests must not reach the archive")

    handler = _handler({"records": [_record()]})
    sent = _capture(handler)
    monkeypatch.setattr(server, "STATE", SimpleNamespace(archive=object()))
    monkeypatch.setattr(server, "BUNDLE_RATE_LIMITER", Allow())
    monkeypatch.setattr(server, "BUNDLE_VERIFY_SLOTS", Busy())
    monkeypatch.setattr(server, "verify_bundle", verification_must_not_run)

    handler.do_POST()

    assert sent["status"] == 503
    assert sent["headers"] == {
        "Retry-After": str(server.BUNDLE_BUSY_RETRY_SECONDS),
    }
    assert sent["body"]["retry_after"] == server.BUNDLE_BUSY_RETRY_SECONDS
    assert "busy" in sent["body"]["why"]


def test_verification_slot_is_released_when_archive_check_raises(monkeypatch) -> None:
    class Allow:
        def check(self, peer: str) -> tuple[bool, int]:
            return True, 0

    class Slot:
        released = 0

        def acquire(self, *, blocking: bool) -> bool:
            assert blocking is False
            return True

        def release(self) -> None:
            self.released += 1

    slot = Slot()
    handler = _handler({"records": [_record()]})
    _capture(handler)
    monkeypatch.setattr(server, "STATE", SimpleNamespace(archive=object()))
    monkeypatch.setattr(server, "BUNDLE_RATE_LIMITER", Allow())
    monkeypatch.setattr(server, "BUNDLE_VERIFY_SLOTS", slot)
    monkeypatch.setattr(
        server,
        "verify_bundle",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("archive down")),
    )

    with pytest.raises(RuntimeError, match="archive down"):
        handler.do_POST()

    assert slot.released == 1


def test_rate_limit_uses_direct_peer_not_forwarding_header(monkeypatch) -> None:
    class Observe:
        def check(self, peer: str) -> tuple[bool, int]:
            assert peer == "192.0.2.44"
            return False, 11

    handler = _handler(
        {"records": [_record()]}, forwarded_for="203.0.113.99, 10.0.0.2",
    )
    sent = _capture(handler)
    monkeypatch.setattr(server, "STATE", SimpleNamespace(archive=object()))
    monkeypatch.setattr(server, "BUNDLE_RATE_LIMITER", Observe())

    handler.do_POST()

    assert sent["status"] == 429
    assert sent["body"]["retry_after"] == 11
