"""The public portal should degrade narrowly when optional work is expensive."""

from __future__ import annotations

import io
import json
import re
from types import SimpleNamespace

import concordance.server as server
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


def test_maplibre_is_loaded_without_blocking_the_local_portal() -> None:
    html = render(PORTAL_STATE)

    # A normal external script blocks parsing, and a normal stylesheet can
    # delay the inline script behind it. Neither MapLibre asset is emitted in a
    # parser-blocking tag now; both are created after local navigation is live.
    assert not re.search(
        r'<script[^>]+src="https://unpkg\.com/maplibre-gl', html,
        flags=re.IGNORECASE,
    )
    assert not re.search(
        r'<link[^>]+href="https://unpkg\.com/maplibre-gl', html,
        flags=re.IGNORECASE,
    )
    navigation = html.index('document.querySelectorAll(".nav-button")')
    network_start = html.index("document.head.appendChild(script)")
    assert navigation < network_start
    assert html.index("const LOADERS = {") < html.rindex("loadMapLibrary();")
    assert 'const script = document.createElement("script")' in html
    assert "script.async = true" in html


def test_a_hanging_map_load_reaches_a_visible_degraded_state() -> None:
    html = render(PORTAL_STATE)

    assert "const MAP_LOAD_TIMEOUT_MS = 4000" in html
    assert "window.setTimeout" in html
    assert '"timed-out"' in html
    assert "Every other view is available from local data." in html
    # The load listener remains installed after the timeout so a slow CDN can
    # still replace the message with the working map.
    assert 'script.addEventListener("load"' in html
    assert "initializeMap();" in html


def test_external_text_is_escaped_before_it_reaches_innerhtml() -> None:
    html = render(PORTAL_STATE)

    # Model output, server errors, OCR-derived decision fields, contribution
    # metadata, and free-form notes all cross a trust boundary. Keep the
    # expected wrappers explicit so a future view cannot quietly regress to
    # interpolating one of them as markup.
    expected = (
        "${esc(d.error)}",
        "${esc(d.reply)}",
        '"<code>"+esc(t.tool)+"</code>"',
        "${esc(d.message)}",
        "${esc(d.caveat)}",
        "${esc(r.river)}",
        "${esc(x.outcome)}",
        '${esc((x.against||[]).join(", ") || "—")}',
        '${esc((p.roles||[])[0]||"")}',
        "${esc(x.person)}",
        "+ esc(d.what_happens_now);",
        '${esc(r.claim_id)}',
        "${esc(n)}",
    )
    for fragment in expected:
        assert fragment in html

    unsafe = (
        "${d.error}",
        "${d.reply}",
        "${t.tool}",
        "${x.outcome}",
        "${x.person}",
        "${d.what_happens_now}",
        "+ d.what_happens_now",
        "${r.claim_id}",
    )
    for fragment in unsafe:
        assert fragment not in html


def test_external_urls_are_scheme_checked_before_becoming_attributes() -> None:
    html = render(PORTAL_STATE)

    assert "const safeHttpUrl = value =>" in html
    assert 'url.protocol === "http:" || url.protocol === "https:"' in html
    assert "safeHttpUrl(x.page_url)" in html
    assert "safeHttpUrl(d.page_url)" in html
    assert "safeHttpUrl(d.crop_url)" in html
    assert "safeHttpUrl(r.page_url)" in html
    assert "safeHttpUrl(r.crop_url)" in html
    for raw_attribute in (
        'href="${x.page_url}"',
        'href="${d.page_url}"',
        'src="${d.crop_url}"',
        'href="${r.page_url}"',
        'src="${r.crop_url}"',
    ):
        assert raw_attribute not in html


def test_citation_image_failure_keeps_an_escaped_page_fallback() -> None:
    html = render(PORTAL_STATE)

    assert "esc(d.note || d.error)" in html
    assert "open the whole page ↗" in html
    assert 'pageUrl ? `<a href="${pageUrl}"' in html
    assert 'cropUrl = safeHttpUrl(d.crop_url)' in html


def test_bundle_limiter_is_a_per_peer_sliding_window() -> None:
    limiter = server._BundleRateLimiter(limit=3, window=60.0)

    assert limiter.check("192.0.2.1", now=0.0) == (True, 0)
    assert limiter.check("192.0.2.1", now=1.0) == (True, 0)
    assert limiter.check("192.0.2.1", now=2.0) == (True, 0)
    assert limiter.check("192.0.2.1", now=3.0) == (False, 57)
    assert limiter.check("198.51.100.8", now=3.0) == (True, 0)
    assert limiter.check("192.0.2.1", now=60.0) == (True, 0)


def _bare_handler(path: str, body: bytes = b"") -> server.Handler:
    handler = object.__new__(server.Handler)
    handler.path = path
    handler.client_address = ("192.0.2.44", 4567)
    handler.headers = {
        "Content-Length": str(len(body)),
        "Content-Type": "application/json",
        "Host": "localhost:8765",
    }
    handler.rfile = io.BytesIO(body)
    return handler


def test_bundle_limit_returns_json_429_before_archive_verification(monkeypatch) -> None:
    class DenyAll:
        def check(self, peer: str) -> tuple[bool, int]:
            assert peer == "192.0.2.44"
            return False, 23

    def verification_must_not_run(*args, **kwargs):
        raise AssertionError("rate-limited bundles must not reach the archive")

    body = json.dumps({"records": [{}]}).encode()
    handler = _bare_handler("/api/bundle", body)
    sent: dict = {}
    handler._send = lambda payload, ctype, **kwargs: sent.update(
        body=json.loads(payload), ctype=ctype, **kwargs,
    )
    monkeypatch.setattr(server, "STATE", SimpleNamespace(archive=object()))
    monkeypatch.setattr(server, "BUNDLE_RATE_LIMITER", DenyAll())
    monkeypatch.setattr(server, "verify_bundle", verification_must_not_run)

    handler.do_POST()

    assert sent["status"] == 429
    assert sent["headers"] == {"Retry-After": "23"}
    assert sent["body"] == {
        "accepted": False,
        "why": "too many bundle submissions; try again later",
        "retry_after": 23,
    }


def test_send_writes_the_requested_http_status_and_retry_header() -> None:
    handler = object.__new__(server.Handler)
    seen: list[tuple] = []
    handler.send_response = lambda status: seen.append(("status", status))
    handler.send_header = lambda name, value: seen.append(("header", name, value))
    handler.end_headers = lambda: seen.append(("end",))
    handler.wfile = io.BytesIO()

    handler._send(
        b"{}", "application/json", status=429, headers={"Retry-After": "12"},
    )

    assert ("status", 429) in seen
    assert ("header", "Retry-After", "12") in seen
    assert handler.wfile.getvalue() == b"{}"


def test_ordinary_navigation_does_not_consult_the_bundle_limiter(monkeypatch) -> None:
    class LimiterMustNotRun:
        def check(self, peer: str) -> tuple[bool, int]:
            raise AssertionError("GET navigation must not share the bundle limit")

    handler = _bare_handler("/")
    sent: dict = {}
    handler._send = lambda payload, ctype, **kwargs: sent.update(
        body=payload, ctype=ctype, **kwargs,
    )
    monkeypatch.setattr(server, "STATE", SimpleNamespace(html=lambda: "portal"))
    monkeypatch.setattr(server, "BUNDLE_RATE_LIMITER", LimiterMustNotRun())

    handler.do_GET()

    assert sent == {"body": b"portal", "ctype": "text/html; charset=utf-8"}


def test_public_portal_does_not_offer_an_unsafe_server_read_button() -> None:
    html = render(PORTAL_STATE)

    assert "/api/read" not in html
    assert 'id="read-now"' not in html
    assert "safe one-click browser-to-local handoff is fellowship work" in html


def test_server_read_get_is_explicitly_disabled(monkeypatch) -> None:
    handler = _bare_handler("/api/read?place=Belleville")
    sent: dict = {}
    handler._send = lambda payload, ctype, **kwargs: sent.update(
        body=json.loads(payload), ctype=ctype, **kwargs,
    )
    monkeypatch.setattr(server, "STATE", object())

    handler.do_GET()

    assert sent["status"] == 501
    assert "server-side reading is disabled" in sent["body"]["error"]
    assert "extract_place.py" in sent["body"]["local_reader"]
