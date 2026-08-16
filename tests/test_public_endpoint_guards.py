"""Adversarial boundaries for public work and mutation endpoints."""

from __future__ import annotations

import io
import json
import threading
from types import SimpleNamespace
from typing import Any

import pytest

import concordance.server as server
from concordance.disputes import Claim, Flag, Ledger, Slot, Standing
from concordance.portal import render


PORTAL_STATE = {
    "corpus_items": 104241,
    "located": 102,
    "read": 14,
    "records": 5147,
    "precision": 0.968,
    "silent_n": 72,
    "silent_year": 1975,
}


def _handler(
    path: str,
    payload: Any | None = None,
    *,
    content_type: str = "application/json",
    origin: str = "",
    host: str = "localhost:8765",
) -> tuple[server.Handler, dict[str, Any]]:
    body = b"" if payload is None else json.dumps(payload).encode()
    handler = object.__new__(server.Handler)
    handler.path = path
    handler.client_address = ("192.0.2.44", 4567)
    handler.headers = {
        "Content-Length": str(len(body)),
        "Content-Type": content_type,
        "Host": host,
        "X-Forwarded-For": "203.0.113.99",
        "X-Forwarded-Host": "evil.example",
    }
    if origin:
        handler.headers["Origin"] = origin
    handler.rfile = io.BytesIO(body)
    sent: dict[str, Any] = {}

    def capture(raw: bytes, ctype: str, **kwargs: Any) -> None:
        sent.update(
            body=json.loads(raw),
            ctype=ctype,
            status=kwargs.get("status", 200),
            headers=kwargs.get("headers") or {},
        )

    handler._send = capture
    return handler, sent


class _WorkMustNotRun:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"guarded request reached expensive work: {name}")


class _Allow:
    def check(self, peer: str) -> tuple[bool, int]:
        # The property defended: limits key on the DIRECT peer. The /api/ask
        # tests run as loopback (the endpoint refuses non-local machines);
        # every other endpoint's tests use the public fixture address. What
        # must never appear here is the forged X-Forwarded-For.
        assert peer in ("192.0.2.44", "127.0.0.1")
        return True, 0


class _Deny:
    def __init__(self, retry_after: int = 17) -> None:
        self.retry_after = retry_after

    def check(self, peer: str) -> tuple[bool, int]:
        # Forwarded headers above deliberately name a different address.
        assert peer in ("192.0.2.44", "127.0.0.1")
        return False, self.retry_after


class _Busy:
    def acquire(self, *, blocking: bool) -> bool:
        assert blocking is False
        return False

    def release(self) -> None:
        raise AssertionError("an unacquired slot must not be released")


class _Slot:
    def __init__(self) -> None:
        self.released = 0

    def acquire(self, *, blocking: bool) -> bool:
        assert blocking is False
        return True

    def release(self) -> None:
        self.released += 1


@pytest.mark.parametrize(
    "path",
    [
        "/api/ask?q=run",
        "/api/bundle?records=anything",
        "/api/citation?identifier=item&page=1",
        "/api/decisions?identifier=item",
        "/api/flag?claim=abc&reason=x",
        "/api/frontier",
        "/api/ledger",
        "/api/submit?identifier=item&page=1&quote=x",
        "/api/watershed",
    ],
)
def test_get_cannot_start_work_or_mutate(monkeypatch, path: str) -> None:
    flags: list[Any] = []
    handler, sent = _handler(path)
    monkeypatch.setattr(server, "FLAGS", flags)
    monkeypatch.setattr(
        server,
        "STATE",
        SimpleNamespace(jay=_WorkMustNotRun(), archive=_WorkMustNotRun()),
    )

    handler.do_GET()

    assert sent["status"] == 405
    assert sent["headers"] == {"Allow": "POST"}
    assert flags == []


@pytest.mark.parametrize("path,payload", [
    ("/api/flag", {"claim": "abc", "reason": "x"}),
    ("/api/bundle", {"records": [{}]}),
])
def test_cross_origin_json_is_rejected_before_mutation_or_archive(
    monkeypatch, path: str, payload: dict[str, Any],
) -> None:
    handler, sent = _handler(
        path, payload, origin="https://evil.example", host="concordance.test",
    )
    monkeypatch.setattr(server, "FLAGS", [])
    monkeypatch.setattr(
        server,
        "STATE",
        SimpleNamespace(archive=_WorkMustNotRun(), invalidate_ledger=_WorkMustNotRun()),
    )
    monkeypatch.setattr(
        server, "verify_bundle",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("cross-origin bundle reached archive verification")
        ),
    )

    handler.do_POST()

    assert sent["status"] == 403
    assert server.FLAGS == []


@pytest.mark.parametrize("path,payload", [
    ("/api/flag", {"claim": "abc"}),
    ("/api/bundle", {"records": [{}]}),
])
def test_simple_text_plain_posts_are_rejected(
    monkeypatch, path: str, payload: dict[str, Any],
) -> None:
    handler, sent = _handler(path, payload, content_type="text/plain")
    monkeypatch.setattr(server, "STATE", _WorkMustNotRun())
    monkeypatch.setattr(server, "FLAGS", [])

    handler.do_POST()

    assert sent["status"] == 415
    assert server.FLAGS == []


def test_oversized_request_is_413_without_reading_or_running_work(monkeypatch) -> None:
    handler, sent = _handler("/api/ask", {"question": "small"})
    handler.client_address = ("127.0.0.1", 4567)  # the gate: local machines only
    handler.headers["Content-Length"] = str(server.MAX_API_JSON_BYTES + 1)

    class _Unreadable:
        def read(self, size: int) -> bytes:
            raise AssertionError("oversized request body must not be read")

    handler.rfile = _Unreadable()
    monkeypatch.setattr(server, "STATE", _WorkMustNotRun())

    handler.do_POST()

    assert sent["status"] == 413


@pytest.mark.parametrize(
    "path,payload,limiter_name",
    [
        (
            "/api/ask",
            {"question": "x" * (server.MAX_QUESTION_CHARS + 1)},
            "MODEL_RATE_LIMITER",
        ),
        (
            "/api/citation",
            {
                "identifier": "item",
                "page": 1,
                "quote": "x" * (server.MAX_QUOTE_CHARS + 1),
            },
            "ARCHIVE_RATE_LIMITER",
        ),
        (
            "/api/decisions",
            {
                "identifier": "item",
                "body": "x" * (server.MAX_DECISION_BODY_CHARS + 1),
            },
            "ARCHIVE_RATE_LIMITER",
        ),
        (
            "/api/flag",
            {"claim": "abc", "reason": "x" * (server.MAX_FLAG_REASON_CHARS + 1)},
            "MUTATION_RATE_LIMITER",
        ),
    ],
)
def test_oversized_fields_are_413_before_rate_or_work(
    monkeypatch, path: str, payload: dict[str, Any], limiter_name: str,
) -> None:
    handler, sent = _handler(path, payload)
    if path == "/api/ask":
        # The mechanics contract applies where the endpoint operates: /api/ask
        # serves only the local machine, so its size cap is tested from one.
        handler.client_address = ("127.0.0.1", 4567)
    monkeypatch.setattr(server, "STATE", _WorkMustNotRun())
    monkeypatch.setattr(server, limiter_name, _WorkMustNotRun())
    monkeypatch.setattr(server, "FLAGS", [])

    handler.do_POST()

    assert sent["status"] == 413
    assert server.FLAGS == []


def test_model_rate_limit_is_per_direct_peer_and_skips_model(monkeypatch) -> None:
    handler, sent = _handler("/api/ask", {"question": "What happened?"})
    handler.client_address = ("127.0.0.1", 4567)  # the gate: local machines only
    monkeypatch.setattr(server, "STATE", SimpleNamespace(jay=_WorkMustNotRun()))
    monkeypatch.setattr(server, "MODEL_RATE_LIMITER", _Deny(19))

    handler.do_POST()

    assert sent["status"] == 429
    assert sent["headers"] == {"Retry-After": "19"}
    assert sent["body"]["retry_after"] == 19


def test_model_busy_is_nonblocking_and_skips_model(monkeypatch) -> None:
    handler, sent = _handler("/api/ask", {"question": "What happened?"})
    handler.client_address = ("127.0.0.1", 4567)  # the gate: local machines only
    monkeypatch.setattr(server, "STATE", SimpleNamespace(jay=_WorkMustNotRun()))
    monkeypatch.setattr(server, "MODEL_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "MODEL_SLOTS", _Busy())

    handler.do_POST()

    assert sent["status"] == 503
    assert sent["headers"] == {
        "Retry-After": str(server.MODEL_BUSY_RETRY_SECONDS),
    }


def test_archive_rate_limit_skips_archive(monkeypatch) -> None:
    handler, sent = _handler(
        "/api/citation", {"identifier": "item", "page": 1, "quote": "x"},
    )
    monkeypatch.setattr(server, "STATE", SimpleNamespace(archive=_WorkMustNotRun()))
    monkeypatch.setattr(server, "ARCHIVE_RATE_LIMITER", _Deny(13))

    handler.do_POST()

    assert sent["status"] == 429
    assert sent["headers"] == {"Retry-After": "13"}


def test_archive_busy_is_nonblocking_and_skips_archive(monkeypatch) -> None:
    handler, sent = _handler(
        "/api/citation", {"identifier": "item", "page": 1, "quote": "x"},
    )
    monkeypatch.setattr(server, "STATE", SimpleNamespace(archive=_WorkMustNotRun()))
    monkeypatch.setattr(server, "ARCHIVE_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "ARCHIVE_SLOTS", _Busy())

    handler.do_POST()

    assert sent["status"] == 503
    assert sent["headers"] == {
        "Retry-After": str(server.ARCHIVE_BUSY_RETRY_SECONDS),
    }


@pytest.mark.parametrize("endpoint,method_name", [
    ("ledger", "ledger"),
    ("watershed", "watershed"),
    ("frontier", "frontier"),
])
def test_expensive_views_share_archive_rate_budget_before_work(
    monkeypatch, endpoint: str, method_name: str,
) -> None:
    state = SimpleNamespace()
    setattr(
        state,
        method_name,
        lambda: (_ for _ in ()).throw(
            AssertionError("rate-limited evidence view did work")
        ),
    )
    handler, sent = _handler(f"/api/{endpoint}", {})
    monkeypatch.setattr(server, "STATE", state)
    monkeypatch.setattr(server, "ARCHIVE_RATE_LIMITER", _Deny(14))

    handler.do_POST()

    assert sent["status"] == 429
    assert sent["headers"] == {"Retry-After": "14"}


def test_expensive_view_busy_path_is_nonblocking(monkeypatch) -> None:
    handler, sent = _handler("/api/ledger", {})
    monkeypatch.setattr(
        server,
        "STATE",
        SimpleNamespace(
            ledger=lambda: (_ for _ in ()).throw(
                AssertionError("busy evidence view did work")
            ),
        ),
    )
    monkeypatch.setattr(server, "ARCHIVE_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "ARCHIVE_SLOTS", _Busy())

    handler.do_POST()

    assert sent["status"] == 503
    assert sent["headers"] == {
        "Retry-After": str(server.ARCHIVE_BUSY_RETRY_SECONDS),
    }


def test_expensive_view_releases_slot_when_state_work_raises(monkeypatch) -> None:
    slot = _Slot()
    handler, sent = _handler("/api/ledger", {})
    monkeypatch.setattr(
        server,
        "STATE",
        SimpleNamespace(
            ledger=lambda: (_ for _ in ()).throw(RuntimeError("archive down")),
        ),
    )
    monkeypatch.setattr(server, "ARCHIVE_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "ARCHIVE_SLOTS", slot)

    handler.do_POST()

    assert sent["status"] == 502
    assert slot.released == 1


def test_duplicate_cold_view_waiter_does_not_consume_archive_slot(monkeypatch) -> None:
    build_lock = threading.Lock()
    build_lock.acquire()

    class _BuildingState:
        @staticmethod
        def evidence_cached(view: str) -> bool:
            assert view == "ledger"
            return False

        @staticmethod
        def evidence_build_lock(view: str) -> threading.Lock:
            assert view == "ledger"
            return build_lock

        @staticmethod
        def ledger() -> dict[str, Any]:
            raise AssertionError("duplicate waiter must not enter the build")

    slots = threading.BoundedSemaphore(3)
    handler, sent = _handler("/api/ledger", {})
    monkeypatch.setattr(server, "STATE", _BuildingState())
    monkeypatch.setattr(server, "ARCHIVE_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "ARCHIVE_SLOTS", slots)

    handler.do_POST()

    assert sent["status"] == 503
    acquired = [slots.acquire(blocking=False) for _ in range(4)]
    assert acquired == [True, True, True, False]
    for _ in range(3):
        slots.release()
    build_lock.release()


def test_warm_view_is_rechecked_under_gate_before_skipping_archive_slot(
    monkeypatch,
) -> None:
    class _RaceState:
        def __init__(self) -> None:
            self.lock = threading.Lock()
            self.cached = True
            self.builds = 0

        def evidence_build_lock(self, view: str) -> threading.Lock:
            return self.lock

        def evidence_cached(self, view: str) -> bool:
            # Simulate accepted-data invalidation before the gate is acquired.
            self.cached = False
            return self.cached

        def build_evidence_view(self, view: str) -> dict[str, bool]:
            self.builds += 1
            self.cached = True
            return {"built": True}

        def ledger(self) -> dict[str, bool]:
            if not self.cached:
                raise AssertionError("cold work bypassed the single-flight builder")
            return {"built": False}

    state = _RaceState()
    slot = _Slot()
    handler, sent = _handler("/api/ledger", {})
    monkeypatch.setattr(server, "STATE", state)
    monkeypatch.setattr(server, "ARCHIVE_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "ARCHIVE_SLOTS", slot)

    handler.do_POST()

    assert sent["status"] == 200
    assert sent["body"] == {"built": True}
    assert state.builds == 1
    assert slot.released == 1


def test_mutation_rate_limit_prevents_flag_append(monkeypatch) -> None:
    handler, sent = _handler("/api/flag", {"claim": "abc", "reason": "x"})
    monkeypatch.setattr(server, "STATE", SimpleNamespace(invalidate_ledger=lambda: None))
    monkeypatch.setattr(server, "MUTATION_RATE_LIMITER", _Deny())
    monkeypatch.setattr(server, "FLAGS", [])

    handler.do_POST()

    assert sent["status"] == 429
    assert server.FLAGS == []


def test_nonexistent_flag_is_inert_and_does_not_invalidate_evidence(monkeypatch) -> None:
    class _State:
        def has_claim(self, claim_id: str) -> bool:
            assert claim_id == "does-not-exist"
            return False

        def invalidate_ledger(self) -> None:
            raise AssertionError("a flag must never invalidate resolved evidence")

    handler, sent = _handler(
        "/api/flag", {"claim": "does-not-exist", "reason": "wrong"},
    )
    monkeypatch.setattr(server, "STATE", _State())
    monkeypatch.setattr(server, "MUTATION_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "FLAGS", [])

    handler.do_POST()

    assert sent["status"] == 404
    assert server.FLAGS == []


def test_repeated_flag_from_one_peer_is_counted_once(monkeypatch) -> None:
    class _State:
        @staticmethod
        def has_claim(claim_id: str) -> bool:
            return claim_id == "abc"

    monkeypatch.setattr(server, "STATE", _State())
    monkeypatch.setattr(server, "MUTATION_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "FLAGS", [])
    monkeypatch.setattr(server, "FLAG_KEYS", set())

    first, first_sent = _handler("/api/flag", {"claim": "abc", "reason": "x"})
    second, second_sent = _handler("/api/flag", {"claim": "abc", "reason": "again"})
    first.do_POST()
    second.do_POST()

    assert first_sent["status"] == second_sent["status"] == 200
    assert first_sent["body"]["recorded"] is True
    assert second_sent["body"]["recorded"] is False
    assert len(server.FLAGS) == 1
    assert server.FLAGS[0].reason == "x"


def test_matching_hostile_origin_and_host_are_rejected(monkeypatch) -> None:
    handler, sent = _handler(
        "/api/ask",
        {"question": "run local work"},
        host="attacker.example:8765",
        origin="http://attacker.example:8765",
    )
    monkeypatch.delenv("CONCORDANCE_PUBLIC_HOSTS", raising=False)
    monkeypatch.setattr(server, "STATE", _WorkMustNotRun())

    handler.do_POST()

    assert sent["status"] == 403
    assert "Host" in sent["body"]["error"]


def test_explicit_public_host_can_be_configured(monkeypatch) -> None:
    class _Jay:
        def ask(self, question: str) -> Any:
            return SimpleNamespace(reply="answer", tool_calls=[], error=None)

    handler, sent = _handler(
        "/api/ask",
        {"question": "What happened?"},
        host="concordance.example",
        origin="https://concordance.example",
    )
    monkeypatch.setenv("CONCORDANCE_PUBLIC_HOSTS", "concordance.example")
    monkeypatch.setattr(server, "STATE", SimpleNamespace(jay=_Jay()))
    monkeypatch.setattr(server, "MODEL_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "MODEL_SLOTS", _Slot())

    handler.do_POST()

    # The configured public host passes the same-origin check -- and is then
    # refused anyway, because Jay runs the local model and a shared instance
    # does not spend its card for visitors. The refusal names the command
    # that works instead.
    assert sent["status"] == 501
    assert "local" in json.dumps(sent["body"]).lower()


@pytest.mark.parametrize(
    "path,payload",
    [
        (
            "/api/bundle",
            {"records": [{
                "kind": "observation", "parameter": "BOD", "value": 1,
                "unit": "mg/L", "provenance": {
                    "identifier": "outside-item", "page": 1,
                    "source_text": "BOD was 1 mg/L.",
                },
            }]},
        ),
        ("/api/citation", {"identifier": "outside-item", "page": 1}),
        ("/api/decisions", {"identifier": "outside-item"}),
        (
            "/api/submit",
            {"identifier": "outside-item", "page": 1,
             "quote": "BOD was 1 mg/L.", "parameter": "BOD", "value": 1},
        ),
    ],
)
def test_public_archive_work_rejects_items_outside_configured_collection(
    monkeypatch, path, payload,
) -> None:
    class _State:
        archive = _WorkMustNotRun()

        @staticmethod
        def allows_archive_identifier(identifier: str) -> bool:
            assert identifier == "outside-item"
            return False

    handler, sent = _handler(path, payload)
    monkeypatch.setattr(server, "STATE", _State())

    handler.do_POST()

    assert sent["status"] == 400
    message = sent["body"].get("error") or sent["body"].get("why")
    assert "outside the configured collection" in message


def test_flags_are_a_cheap_overlay_and_never_reresolve_archive(monkeypatch) -> None:
    record = {
        "kind": "observation",
        "parameter": "BOD",
        "value": 1,
        "unit": "mg/L",
        "place": "Example",
        "period": "1970",
        "provenance": {
            "identifier": "item",
            "page": 1,
            "source_text": "BOD was 1 mg/L.",
        },
    }
    claim = Claim(record=record)
    standing = Standing(claim=claim, verified=True, why="verified")
    resolved = Ledger(slots={claim.slot: Slot(claim.slot, standings=[standing])})
    calls = 0

    def resolve_once(*args: Any, **kwargs: Any) -> Ledger:
        nonlocal calls
        calls += 1
        return resolved

    state = object.__new__(server.State)
    state._ledger_lock = threading.Lock()
    state._ledger_base = None
    state._ledger_claim_slots = {}
    state._ledger_slot_meta = {}
    state._claims = [claim]
    state.archive = object()
    monkeypatch.setattr(server, "resolve_claims", resolve_once)
    monkeypatch.setattr(server, "FLAGS", [])

    first = state.ledger()
    server.FLAGS.extend([
        Flag(claim_id="not-a-real-claim", reason="noise"),
        Flag(claim_id=claim.id, reason="check this"),
    ])
    second = state.ledger()

    assert calls == 1
    assert first["flags"] == 0
    assert second["flags"] == 1
    assert second["most_flagged"] == [{
        "slot": claim.slot,
        "flags": 1,
        "state": "settled",
        "values": [1],
        "reasons": ["check this"],
    }]


def test_watershed_failure_result_is_cached_instead_of_retried() -> None:
    state = object.__new__(server.State)
    state._watershed = None
    state._watershed_lock = threading.Lock()
    calls = 0

    def build() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"rivers": [], "error": "ECCC unavailable"}

    state._build_watershed = build

    assert state.watershed()["error"] == "ECCC unavailable"
    assert state.watershed()["error"] == "ECCC unavailable"
    assert calls == 1


def test_submit_busy_path_does_not_call_archive_submission(monkeypatch) -> None:
    payload = {
        "identifier": "item",
        "page": 1,
        "quote": "BOD was 1 mg/L.",
        "parameter": "BOD",
        "value": 1,
        "unit": "mg/L",
    }
    handler, sent = _handler("/api/submit", payload)
    monkeypatch.setattr(server, "STATE", SimpleNamespace(archive=object()))
    monkeypatch.setattr(server, "MUTATION_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "ARCHIVE_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "ARCHIVE_SLOTS", _Busy())
    monkeypatch.setattr(
        server, "submit_claim",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("busy submit reached archive")
        ),
    )

    handler.do_POST()

    assert sent["status"] == 503


def test_accepted_submit_reloads_corpus_and_passes_contribution_directory(
    monkeypatch, tmp_path,
) -> None:
    payload = {
        "identifier": "item",
        "page": 1,
        "quote": "BOD was 1 mg/L.",
        "parameter": "BOD",
        "value": 1,
        "unit": "mg/L",
    }
    contribution_dir = tmp_path / "contributions"
    reloads = 0

    class _State:
        archive = object()

        def reload(self) -> None:
            nonlocal reloads
            reloads += 1

    class _Outcome:
        standing = SimpleNamespace(verified=True)
        stored = True

        @staticmethod
        def to_dict() -> dict[str, Any]:
            return {"accepted": True, "stored": True}

    def submit(*args: Any, **kwargs: Any) -> _Outcome:
        assert kwargs["directory"] == contribution_dir
        return _Outcome()

    handler, sent = _handler("/api/submit", payload)
    monkeypatch.setattr(server, "STATE", _State())
    monkeypatch.setattr(server, "CONTRIBUTIONS", contribution_dir)
    monkeypatch.setattr(server, "MUTATION_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "ARCHIVE_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "ARCHIVE_SLOTS", _Slot())
    monkeypatch.setattr(server, "submit_claim", submit)

    handler.do_POST()

    assert sent["status"] == 200
    assert sent["body"]["accepted"] is True
    assert reloads == 1


def test_verified_duplicate_submit_does_not_invalidate_caches(monkeypatch) -> None:
    payload = {
        "identifier": "item", "page": 1, "quote": "BOD was 1 mg/L.",
        "parameter": "BOD", "value": 1, "unit": "mg/L",
    }
    reloads = 0

    class _State:
        archive = object()

        def reload(self) -> None:
            nonlocal reloads
            reloads += 1

    outcome = SimpleNamespace(
        standing=SimpleNamespace(verified=True), stored=False,
        to_dict=lambda: {"accepted": True, "stored": False},
    )
    handler, sent = _handler("/api/submit", payload)
    monkeypatch.setattr(server, "STATE", _State())
    monkeypatch.setattr(server, "MUTATION_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "ARCHIVE_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "ARCHIVE_SLOTS", _Slot())
    monkeypatch.setattr(server, "submit_claim", lambda *args, **kwargs: outcome)

    handler.do_POST()

    assert sent["status"] == 200
    assert reloads == 0


def test_accepted_bundle_reloads_corpus_for_jay_and_library(monkeypatch) -> None:
    bundle = {
        "records": [{
            "kind": "observation",
            "parameter": "BOD",
            "value": 1,
            "provenance": {
                "identifier": "item",
                "page": 1,
                "source_text": "BOD was 1 mg/L.",
            },
        }],
    }
    reloads = 0

    class _State:
        archive = object()

        def reload(self) -> None:
            nonlocal reloads
            reloads += 1

    verdict = SimpleNamespace(failed=[], verified=1, accepted=True)
    handler, sent = _handler("/api/bundle", bundle)
    monkeypatch.setattr(server, "STATE", _State())
    monkeypatch.setattr(server, "BUNDLE_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "BUNDLE_VERIFY_SLOTS", _Slot())
    monkeypatch.setattr(server, "verify_bundle", lambda *args, **kwargs: verdict)
    monkeypatch.setattr(
        server,
        "merge_bundle",
        lambda *args, **kwargs: {"accepted": 1, "duplicates_dropped": 0},
    )

    handler.do_POST()

    assert sent["status"] == 200
    assert sent["body"]["accepted"] is True
    assert reloads == 1


def test_duplicate_bundle_does_not_invalidate_caches(monkeypatch) -> None:
    bundle = {
        "records": [{
            "kind": "observation", "parameter": "BOD", "value": 1,
            "provenance": {"identifier": "item", "page": 1,
                           "source_text": "BOD was 1 mg/L."},
        }],
    }
    reloads = 0

    class _State:
        archive = object()

        def reload(self) -> None:
            nonlocal reloads
            reloads += 1

    verdict = SimpleNamespace(
        failed=[], unsupported=[], supported=bundle["records"],
        verified=1, accepted=True,
    )
    handler, sent = _handler("/api/bundle", bundle)
    monkeypatch.setattr(server, "STATE", _State())
    monkeypatch.setattr(server, "BUNDLE_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "BUNDLE_VERIFY_SLOTS", _Slot())
    monkeypatch.setattr(server, "verify_bundle", lambda *args, **kwargs: verdict)
    monkeypatch.setattr(
        server, "merge_bundle",
        lambda *args, **kwargs: {"accepted": 0, "duplicates_dropped": 1},
    )

    handler.do_POST()

    assert sent["status"] == 200
    assert sent["body"]["merged"] == 0
    assert sent["body"]["already_here"] == 1
    assert reloads == 0


def test_state_reload_generation_survives_failure_and_concurrent_write(
    monkeypatch,
) -> None:
    """A failed/older snapshot can never clear a newer durable generation."""
    state = object.__new__(server.State)
    state._reload_lock = threading.Lock()
    state._publication_lock = threading.Lock()
    state._durable_generation = 0
    state._published_generation = 0
    state._geocode = lambda corpus: []
    state.invalidate_ledger = lambda: None

    loads = 0

    def load_corpus() -> Any:
        nonlocal loads
        loads += 1
        if loads == 1:
            raise RuntimeError("temporary reload failure")
        if loads == 2:
            # This write lands while generation 1 is being rebuilt. The first
            # successful snapshot may not claim to have published generation 2.
            assert state.mark_reload_needed() == 2
        return SimpleNamespace(records=[], places=[])

    monkeypatch.setattr(server, "_load_public_corpus", load_corpus)
    monkeypatch.setattr(server, "_load_public_claims", lambda: [])
    monkeypatch.setattr(server, "Jay", lambda corpus: SimpleNamespace(corpus=corpus))

    assert state.mark_reload_needed() == 1
    with pytest.raises(RuntimeError, match="temporary reload failure"):
        state.reload_if_needed()
    assert state.reload_needed is True
    assert state._published_generation == 0

    assert state.reload_if_needed() is True
    assert state._published_generation == 1
    assert state.reload_needed is True

    assert state.reload_if_needed() is True
    assert state._published_generation == 2
    assert state.reload_needed is False


def test_bundle_reload_failure_is_reported_and_duplicate_retry_publishes(
    monkeypatch,
) -> None:
    bundle = {
        "records": [{
            "kind": "observation", "parameter": "BOD", "value": 1,
            "provenance": {"identifier": "item", "page": 1,
                           "source_text": "BOD was 1 mg/L."},
        }],
    }

    class _State:
        archive = object()
        pending = 0
        attempts = 0
        marks = 0

        def mark_reload_needed(self) -> int:
            self.marks += 1
            self.pending += 1
            return self.pending

        def reload_if_needed(self) -> bool:
            if not self.pending:
                return False
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("refresh unavailable " + "x" * 300)
            self.pending = 0
            return True

    state = _State()
    verdict = SimpleNamespace(
        failed=[], unsupported=[], supported=bundle["records"],
        verified=1, accepted=True,
    )
    merge_results = iter([
        {"accepted": 1, "duplicates_dropped": 0},
        {"accepted": 0, "duplicates_dropped": 1},
    ])
    monkeypatch.setattr(server, "STATE", state)
    monkeypatch.setattr(server, "BUNDLE_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "BUNDLE_VERIFY_SLOTS", _Slot())
    monkeypatch.setattr(server, "verify_bundle", lambda *args, **kwargs: verdict)
    monkeypatch.setattr(
        server, "merge_bundle", lambda *args, **kwargs: next(merge_results),
    )

    first, first_sent = _handler("/api/bundle", bundle)
    first.do_POST()

    assert first_sent["status"] == 503
    assert first_sent["body"]["accepted"] is True
    assert first_sent["body"]["merged"] == 1
    assert first_sent["body"]["published"] is False
    assert first_sent["body"]["refresh_failed"] is True
    assert len(first_sent["body"]["refresh_error"]) == 160
    assert first_sent["headers"]["Retry-After"]
    assert state.pending == 1

    retry, retry_sent = _handler("/api/bundle", bundle)
    retry.do_POST()

    assert retry_sent["status"] == 200
    assert retry_sent["body"]["merged"] == 0
    assert retry_sent["body"]["already_here"] == 1
    assert retry_sent["body"]["published"] is True
    assert retry_sent["body"]["refresh_failed"] is False
    assert state.pending == 0
    assert state.attempts == 2
    assert state.marks == 1


def test_submit_reload_failure_is_reported_and_duplicate_retry_publishes(
    monkeypatch, tmp_path,
) -> None:
    payload = {
        "identifier": "item", "page": 1, "quote": "BOD was 1 mg/L.",
        "parameter": "BOD", "value": 1, "unit": "mg/L",
    }

    class _State:
        archive = object()
        pending = 0
        attempts = 0
        marks = 0

        def mark_reload_needed(self) -> int:
            self.marks += 1
            self.pending += 1
            return self.pending

        def reload_if_needed(self) -> bool:
            if not self.pending:
                return False
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("live corpus unavailable")
            self.pending = 0
            return True

    class _Outcome:
        standing = SimpleNamespace(verified=True)

        def __init__(self, stored: bool) -> None:
            self.stored = stored

        def to_dict(self) -> dict[str, Any]:
            return {"accepted": True, "stored": self.stored}

    outcomes = iter([_Outcome(True), _Outcome(False)])
    state = _State()
    monkeypatch.setattr(server, "STATE", state)
    monkeypatch.setattr(server, "CONTRIBUTIONS", tmp_path / "contributions")
    monkeypatch.setattr(server, "MUTATION_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "ARCHIVE_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "ARCHIVE_SLOTS", _Slot())
    monkeypatch.setattr(
        server, "submit_claim", lambda *args, **kwargs: next(outcomes),
    )

    first, first_sent = _handler("/api/submit", payload)
    first.do_POST()

    assert first_sent["status"] == 503
    assert first_sent["body"]["accepted"] is True
    assert first_sent["body"]["stored"] is True
    assert first_sent["body"]["published"] is False
    assert first_sent["body"]["refresh_failed"] is True
    assert state.pending == 1

    retry, retry_sent = _handler("/api/submit", payload)
    retry.do_POST()

    assert retry_sent["status"] == 200
    assert retry_sent["body"]["accepted"] is True
    assert retry_sent["body"]["stored"] is False
    assert retry_sent["body"]["published"] is True
    assert retry_sent["body"]["refresh_failed"] is False
    assert state.pending == 0
    assert state.attempts == 2
    assert state.marks == 1


def test_model_slot_releases_when_model_raises(monkeypatch) -> None:
    class _Jay:
        def ask(self, question: str) -> Any:
            raise RuntimeError("model down")

    slot = _Slot()
    handler, sent = _handler("/api/ask", {"question": "What happened?"})
    handler.client_address = ("127.0.0.1", 4567)  # the gate: local machines only
    monkeypatch.setattr(server, "STATE", SimpleNamespace(jay=_Jay()))
    monkeypatch.setattr(server, "MODEL_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "MODEL_SLOTS", slot)

    handler.do_POST()

    assert sent["status"] == 500
    assert slot.released == 1


def test_archive_slot_releases_when_archive_raises(monkeypatch) -> None:
    class _Archive:
        def pages(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("archive down")

    slot = _Slot()
    handler, sent = _handler(
        "/api/citation", {"identifier": "item", "page": 1},
    )
    monkeypatch.setattr(server, "STATE", SimpleNamespace(archive=_Archive()))
    monkeypatch.setattr(server, "ARCHIVE_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "ARCHIVE_SLOTS", slot)

    handler.do_POST()

    assert sent["status"] == 502
    assert slot.released == 1


def test_nonbrowser_json_without_origin_is_allowed(monkeypatch) -> None:
    class _Jay:
        def ask(self, question: str) -> Any:
            return SimpleNamespace(reply="answer", tool_calls=[], error=None)

    handler, sent = _handler("/api/ask", {"question": "What happened?"})
    handler.client_address = ("127.0.0.1", 4567)  # the gate: local machines only
    monkeypatch.setattr(server, "STATE", SimpleNamespace(jay=_Jay()))
    monkeypatch.setattr(server, "MODEL_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "MODEL_SLOTS", _Slot())

    handler.do_POST()

    assert sent["status"] == 200
    assert sent["body"]["reply"] == "answer"


def test_same_origin_uses_real_host_not_forwarded_host(monkeypatch) -> None:
    class _Jay:
        def ask(self, question: str) -> Any:
            return SimpleNamespace(reply="answer", tool_calls=[], error=None)

    handler, sent = _handler(
        "/api/ask",
        {"question": "What happened?"},
        origin="http://localhost:8765",
        host="localhost:8765",
    )
    handler.client_address = ("127.0.0.1", 4567)  # the gate: local machines only
    monkeypatch.setattr(server, "STATE", SimpleNamespace(jay=_Jay()))
    monkeypatch.setattr(server, "MODEL_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "MODEL_SLOTS", _Slot())

    handler.do_POST()

    assert sent["status"] == 200
    assert sent["body"]["reply"] == "answer"


def test_state_publishes_contributions_once_and_rebinds_jay(
    monkeypatch, tmp_path,
) -> None:
    results = tmp_path / "results"
    contributions = tmp_path / "contributions"
    results.mkdir()
    contributions.mkdir()

    def record(value: int, period: str) -> dict[str, Any]:
        return {
            "kind": "observation",
            "parameter": "BOD",
            "value": value,
            "unit": "mg/L",
            "stream": "effluent",
            "place": "Example",
            "period": period,
            "confidence": 1.0,
            "provenance": {
                "identifier": "item",
                "page": value,
                "source_text": f"BOD was {value} mg/L.",
            },
        }

    first = record(1, "1970")
    second = record(2, "1971")
    (results / "example.json").write_text(
        json.dumps({"place": "Example", "records": [first]}), encoding="utf-8",
    )
    (contributions / "accepted-a.json").write_text(
        json.dumps({"records": [first, second]}), encoding="utf-8",
    )

    class _Jay:
        def __init__(self, corpus) -> None:
            self.corpus = corpus

    class _Archive:
        @staticmethod
        def load_index() -> list[dict[str, str]]:
            return [{"identifier": "item"}]

    monkeypatch.setattr(server, "RESULTS", results)
    monkeypatch.setattr(server, "CONTRIBUTIONS", contributions)
    monkeypatch.setattr(server, "Archive", _Archive)
    monkeypatch.setattr(server, "Jay", _Jay)
    monkeypatch.setattr(server, "load_vision_records", lambda: [])

    state = server.State()

    # The duplicate accepted reading collapses by live record identity; the
    # distinct accepted reading appears in the canonical Corpus and Jay.
    assert len(state.corpus.records) == 2
    assert {item.value for item in state.corpus.records} == {1, 2}
    assert state.jay.corpus is state.corpus
    assert len(state._claims) == 2
    assert any(claim.record.get("value") == 2 for claim in state._claims)

    handler, sent = _handler("/api/library.json")
    monkeypatch.setattr(server, "STATE", state)
    handler.do_GET()
    assert sent["body"]["n_records"] == 2
    assert {item["value"] for item in sent["body"]["records"]} == {1, 2}

    old_jay = state.jay
    (contributions / "accepted-b.json").write_text(
        json.dumps({"records": [record(3, "1972")]}), encoding="utf-8",
    )
    state.reload()

    assert len(state.corpus.records) == 3
    assert state.jay is not old_jay
    assert state.jay.corpus is state.corpus


def test_portal_uses_json_post_for_guarded_endpoints() -> None:
    html = render(PORTAL_STATE)

    assert 'method: "POST"' in html
    assert '"Content-Type": "application/json"' in html
    for endpoint in (
        "ask", "citation", "decisions", "flag", "frontier", "ledger",
        "submit", "watershed",
    ):
        assert f'postJson("/api/{endpoint}"' in html
        assert f'fetch("/api/{endpoint}?' not in html


@pytest.mark.parametrize(
    "path",
    [
        "/static/../server.py",
        "/static/C:/Windows/win.ini",
        r"/static/C:\Windows\win.ini",
        r"/static/\\host\share\asset.js",
        "/static/not-public.txt",
    ],
)
def test_unknown_static_paths_fail_before_filesystem_resolution(
    monkeypatch, path,
) -> None:
    handler = object.__new__(server.Handler)
    handler.path = path
    handler.send_error = lambda status: setattr(handler, "sent_status", status)
    monkeypatch.setattr(server, "STATE", object())
    monkeypatch.setattr(
        server.Path,
        "resolve",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("untrusted static path reached resolve")
        ),
    )

    handler.do_GET()

    assert handler.sent_status == 404


def test_allowed_static_name_cannot_follow_a_symlink_outside(
    monkeypatch, tmp_path,
) -> None:
    package = tmp_path / "package"
    static = package / "static"
    static.mkdir(parents=True)
    outside = tmp_path / "outside.css"
    outside.write_text("secret", encoding="utf-8")
    link = static / "omega-portal.css"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable on this platform: {exc}")

    handler = object.__new__(server.Handler)
    handler.path = "/static/omega-portal.css"
    handler.send_error = lambda status: setattr(handler, "sent_status", status)
    handler._send = lambda *args, **kwargs: pytest.fail("escaped asset was read")
    monkeypatch.setattr(server, "STATE", object())
    monkeypatch.setattr(server, "__file__", str(package / "server.py"))

    handler.do_GET()

    assert handler.sent_status == 404


def test_the_browser_reader_is_served_at_an_address_a_person_can_say(
    monkeypatch,
) -> None:
    """/browser serves the in-browser reader demo as HTML -- the address a
    social post or a conversation can hand to someone. It is the same file
    the /static/ allowlist serves; a route that private-cased its own file
    handling would fork the containment discipline."""
    handler = object.__new__(server.Handler)
    handler.path = "/browser"
    sent = {}

    def _send(body, ctype, *a, **kw):
        sent.update(body=body, ctype=ctype)

    handler._send = _send
    handler.send_error = lambda status: sent.update(status=status)
    monkeypatch.setattr(server, "STATE", object())

    handler.do_GET()

    assert "status" not in sent, f"/browser returned {sent.get('status')}"
    assert sent["ctype"].startswith("text/html")
    assert b"Read this page in the browser" in sent["body"]
