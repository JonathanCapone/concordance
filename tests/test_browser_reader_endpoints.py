"""The browser reader's server half: the site hands a visitor's tab the work.

/api/browser/plan serves the SAME document selection the installed reader
uses (`library.plan_documents`), and /api/browser/pages serves exactly the
prose pages, each capped at the prompt length `extract_prose` itself uses --
so a browser read and a local read of one town can never disagree about what
was there to read. Both endpoints are public and therefore bounded before any
expensive work can start.
"""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
from typing import Any

import concordance.router as router
import concordance.server as server
from concordance.library import plan_documents
from concordance.models import PageText


def _handler(
    path: str,
    payload: Any | None = None,
    *,
    host: str = "localhost:8765",
) -> tuple[server.Handler, dict[str, Any]]:
    body = b"" if payload is None else json.dumps(payload).encode()
    handler = object.__new__(server.Handler)
    handler.path = path
    handler.client_address = ("192.0.2.44", 4567)
    handler.headers = {
        "Content-Length": str(len(body)),
        "Content-Type": "application/json",
        "Host": host,
    }
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


class _Allow:
    def check(self, peer: str) -> tuple[bool, int]:
        assert peer == "192.0.2.44"
        return True, 0


class _Deny:
    def check(self, peer: str) -> tuple[bool, int]:
        assert peer == "192.0.2.44"
        return False, 9


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


class _WorkMustNotRun:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"guarded request reached expensive work: {name}")


class _FakeArchive:
    """iter_items with Archive's title filter, and canned pages."""

    def __init__(self, items: list[dict[str, Any]] | None = None,
                 pages: list[PageText] | None = None) -> None:
        self._items = items or []
        self._pages = pages or []

    def iter_items(self, *, title_contains: str | None = None,
                   **_kw: Any) -> Any:
        want = (title_contains or "").lower()
        return (item for item in self._items
                if want in str(item.get("title", "")).lower())

    def pages(self, identifier: str, **_kw: Any) -> list[PageText]:
        return list(self._pages)


# ---- the selection is one definition, shared ---------------------------

def test_plan_documents_is_the_installed_readers_selection() -> None:
    """Reports first, then the rest alphabetically, within the budget."""
    archive = _FakeArchive(items=[
        {"identifier": "z", "title": "Zebra survey of Fergus"},
        {"identifier": "a", "title": "Annual report, Fergus WPCP"},
        {"identifier": "r", "title": "Fergus assessment roll"},
        {"identifier": "x", "title": "Owen Sound annual report"},
    ])
    picked = plan_documents("fergus", archive=archive)  # type: ignore[arg-type]
    assert [item["identifier"] for item in picked] == ["a", "r", "z"]

    capped = plan_documents("fergus", archive=archive,  # type: ignore[arg-type]
                            max_documents=2)
    assert [item["identifier"] for item in capped] == ["a", "r"]


# ---- /api/browser/plan -------------------------------------------------

def test_plan_needs_a_place(monkeypatch) -> None:
    monkeypatch.setattr(server, "STATE",
                        SimpleNamespace(archive=_WorkMustNotRun()))
    handler, sent = _handler("/api/browser/plan", {"place": "  "})
    handler.do_POST()
    assert sent["status"] == 400


def test_plan_is_rate_limited_before_any_index_work(monkeypatch) -> None:
    monkeypatch.setattr(server, "STATE",
                        SimpleNamespace(archive=_WorkMustNotRun()))
    monkeypatch.setattr(server, "ARCHIVE_RATE_LIMITER", _Deny())
    handler, sent = _handler("/api/browser/plan", {"place": "Fergus"})
    handler.do_POST()
    assert sent["status"] == 429
    assert sent["headers"]["Retry-After"] == "9"


def test_plan_reports_busy_instead_of_queueing(monkeypatch) -> None:
    monkeypatch.setattr(server, "STATE",
                        SimpleNamespace(archive=_WorkMustNotRun()))
    monkeypatch.setattr(server, "ARCHIVE_RATE_LIMITER", _Allow())
    monkeypatch.setattr(server, "ARCHIVE_SLOTS", _Busy())
    handler, sent = _handler("/api/browser/plan", {"place": "Fergus"})
    handler.do_POST()
    assert sent["status"] == 503


def test_plan_hands_the_browser_the_readers_own_documents(monkeypatch) -> None:
    """The response carries what the page needs to prompt with and to stamp
    records with -- and normalizes the index's loose shapes (list publishers,
    text imagecounts) so the page never has to know about them."""
    archive = _FakeArchive(items=[
        {"identifier": "fergus-report-1969",
         "title": "Annual report of the Fergus Water Pollution Control Plant",
         "year": 1969, "publisher": ["Ontario Water Resources Commission"],
         "imagecount": "44"},
        {"identifier": "fergus-roll",
         "title": "Fergus assessment roll", "year": "1961"},
    ])
    monkeypatch.setattr(server, "STATE", SimpleNamespace(archive=archive))
    monkeypatch.setattr(server, "ARCHIVE_RATE_LIMITER", _Allow())
    slot = _Slot()
    monkeypatch.setattr(server, "ARCHIVE_SLOTS", slot)
    handler, sent = _handler("/api/browser/plan", {"place": "Fergus"})
    handler.do_POST()

    assert sent["status"] == 200
    body = sent["body"]
    assert body["place"] == "Fergus"
    assert body["max_documents"] == server.MAX_BROWSER_DOCUMENTS
    docs = body["documents"]
    assert [d["identifier"] for d in docs] == ["fergus-report-1969", "fergus-roll"]
    report = docs[0]
    assert report["publisher"] == "Ontario Water Resources Commission"
    assert report["year"] == "1969"
    assert report["leaves"] == 44
    assert report["facility"] == "water pollution control plant"
    assert docs[1]["facility"] == ""
    assert slot.released == 1


# ---- /api/browser/pages ------------------------------------------------

def _pages_state(pages: list[PageText], *, allowed: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        archive=_FakeArchive(pages=pages),
        allows_archive_identifier=lambda identifier: allowed,
    )


def test_pages_needs_an_identifier(monkeypatch) -> None:
    monkeypatch.setattr(server, "STATE",
                        SimpleNamespace(archive=_WorkMustNotRun()))
    handler, sent = _handler("/api/browser/pages", {"identifier": ""})
    handler.do_POST()
    assert sent["status"] == 400


def test_pages_refuses_identifiers_outside_the_collection(monkeypatch) -> None:
    monkeypatch.setattr(server, "STATE", _pages_state([], allowed=False))
    handler, sent = _handler("/api/browser/pages", {"identifier": "not-ours"})
    handler.do_POST()
    assert sent["status"] == 400
    assert "outside the configured collection" in sent["body"]["error"]


def test_pages_is_rate_limited_before_any_archive_work(monkeypatch) -> None:
    state = SimpleNamespace(archive=_WorkMustNotRun(),
                            allows_archive_identifier=lambda i: True)
    monkeypatch.setattr(server, "STATE", state)
    monkeypatch.setattr(server, "ARCHIVE_RATE_LIMITER", _Deny())
    handler, sent = _handler("/api/browser/pages", {"identifier": "item"})
    handler.do_POST()
    assert sent["status"] == 429


def test_pages_serves_prose_pages_only_within_the_budget(monkeypatch) -> None:
    """Only prose-routed pages go out, capped in count and per-page length,
    and what the caps left off is REPORTED rather than implied absent."""
    pages = [
        PageText(identifier="item", page=1, text="table " * 40),
        PageText(identifier="item", page=2, text="alpha beta gamma delta " * 40),
        PageText(identifier="item", page=3, text="epsilon zeta eta theta " * 40),
        PageText(identifier="item", page=4, text="iota kappa lambda mu " * 40),
    ]
    monkeypatch.setattr(server, "STATE", _pages_state(pages))
    monkeypatch.setattr(server, "ARCHIVE_RATE_LIMITER", _Allow())
    slot = _Slot()
    monkeypatch.setattr(server, "ARCHIVE_SLOTS", slot)
    # Route by page number, not by parsing real typography: page 1 is not
    # prose; the rest are. The router's own behavior has its own tests.
    monkeypatch.setattr(
        router, "route",
        lambda page: SimpleNamespace(
            paths=[] if page.page == 1 else [router.Path.PROSE]),
    )
    monkeypatch.setattr(server, "MAX_BROWSER_PROSE_PAGES", 2)
    monkeypatch.setattr(server, "MAX_BROWSER_PAGE_CHARS", 11)

    handler, sent = _handler("/api/browser/pages", {"identifier": "item"})
    handler.do_POST()

    assert sent["status"] == 200
    body = sent["body"]
    assert body["n_pages"] == 4
    assert body["n_prose"] == 3
    assert body["omitted"] == 1
    assert [p["page"] for p in body["pages"]] == [2, 3]
    assert all(len(p["text"]) <= 11 for p in body["pages"])
    assert slot.released == 1


def test_pages_reports_an_unretrievable_document(monkeypatch) -> None:
    class _Boom:
        def pages(self, identifier: str, **_kw: Any) -> list[PageText]:
            raise RuntimeError("archive.org went away")

    state = SimpleNamespace(archive=_Boom(),
                            allows_archive_identifier=lambda i: True)
    monkeypatch.setattr(server, "STATE", state)
    monkeypatch.setattr(server, "ARCHIVE_RATE_LIMITER", _Allow())
    slot = _Slot()
    monkeypatch.setattr(server, "ARCHIVE_SLOTS", slot)
    handler, sent = _handler("/api/browser/pages", {"identifier": "item"})
    handler.do_POST()
    assert sent["status"] == 502
    assert "not retrievable" in sent["body"]["error"]
    assert slot.released == 1


def test_both_browser_endpoints_refuse_get(monkeypatch) -> None:
    monkeypatch.setattr(
        server, "STATE",
        SimpleNamespace(archive=_WorkMustNotRun(), jay=_WorkMustNotRun()),
    )
    for path in ("/api/browser/plan?place=x", "/api/browser/pages?identifier=y"):
        handler, sent = _handler(path)
        handler.do_GET()
        assert sent["status"] == 405
        assert sent["headers"] == {"Allow": "POST"}
