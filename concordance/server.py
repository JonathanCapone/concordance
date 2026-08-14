"""A running instance you can click.

    python -m concordance.server

The server itself is standard library -- `http.server` rather than a framework --
and needs no API key. The map is MapLibre from a CDN, lifted from the OMEGA-wave
portal along with its keyless Esri imagery and AWS terrain tiles.

This is the serving layer, and it is the one part of the project allowed outside
dependencies. The core stays dependency-free so that a stranger can verify a
measurement without standing up a web stack: nobody should have to install a
mapping library to check whether 104 mg/L is what the page actually says.

Everything it serves comes from files already produced by the pipeline. The
server computes nothing it cannot show you the source of.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
import webbrowser
from collections import Counter, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse, urlsplit

from .archive import Archive
from .citations import cite, cite_record
from .contribute import (
    bundle_id, merge_bundle, public_record_key, record_problems, verify_bundle,
)
from .decisions import read_document
from .frontier import load as load_frontier
from .disputes import (
    CONTRIBUTIONS, Flag, load_public_claims, load_vision_records,
    resolve as resolve_claims, submit as submit_claim,
)
from .parameters import resolve as resolve_parameter
from .jay import Jay
from .portal import render
from .reading import READER
from .science import series_from_records
from .tools import Corpus, find_my_town, judge_reading, read_me_the_record, what_went_quiet

RESULTS = Path("data/results")

#: Flags people have raised, in memory. Deliberately not persisted yet: a flag
#: changes nothing about the data by design, so losing them on restart costs a
#: tally and no evidence. Persisting them is a storage decision, not a trust
#: one, and it can wait until there is somewhere to put them.
FLAGS: list[Flag] = []
FLAGS_LOCK = threading.Lock()
# One inert flag per direct peer and claim is enough to show that somebody
# questioned it. Without this bounded identity, a public client can grow the
# process forever by repeating the same no-authority signal.
FLAG_KEYS: set[tuple[str, str]] = set()

#: Largest bundle accepted over HTTP. A shared instance takes uploads from
#: anyone, so both encoded size and verification work need explicit bounds.
MAX_BUNDLE_BYTES = 8 * 1024 * 1024

#: Archive verification fetches every cited item before checking its records.
#: These limits admit the existing municipality-sized exports while preventing
#: a compact JSON body from expanding into unbounded archive and comparison
#: work. A larger contribution can be split into independently verifiable
#: bundles without weakening the evidence carried by any record.
MAX_BUNDLE_RECORDS = 2_000
MAX_BUNDLE_IDENTIFIERS = 25
MAX_BUNDLE_PAGES = 500

#: At most two public submissions may perform archive verification at once.
#: This semaphore is deliberately non-blocking: HTTP worker threads report a
#: temporary 503 instead of piling up behind slow network reads. Like the rate
#: limiter below, this is process-local. A multi-process deployment still needs
#: an equivalent global limit at its process manager or reverse proxy.
BUNDLE_VERIFY_CONCURRENCY = 2
BUNDLE_BUSY_RETRY_SECONDS = 5
BUNDLE_VERIFY_SLOTS = threading.BoundedSemaphore(BUNDLE_VERIFY_CONCURRENCY)

#: Archive verification is the expensive public write path: one bundle can
#: require many remote page reads. Three valid submissions per source address
#: per minute permits an ordinary contribution and a couple of corrections,
#: while bounding a tight retry loop. Navigation and every GET endpoint bypass
#: this limiter entirely.
BUNDLE_RATE_LIMIT = 3
BUNDLE_RATE_WINDOW_SECONDS = 60.0


class _BundleRateLimiter:
    """Process-local sliding window keyed by the direct socket peer address.

    Forwarding headers are intentionally ignored because an unauthenticated
    client can supply them. Consequently, deployments behind a reverse proxy
    see the proxy as one peer and should enforce their per-client policy at that
    trusted edge. This limiter remains a modest direct-peer safety net, not a
    distributed abuse-control system.
    """

    def __init__(self, limit: int, window: float) -> None:
        if limit < 1 or window <= 0:
            raise ValueError("rate-limit values must be positive")
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, *, now: float | None = None) -> tuple[bool, int]:
        """Consume one allowance, or return seconds until another is free."""
        moment = time.monotonic() if now is None else now
        cutoff = moment - self.window
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.limit:
                retry_after = max(1, math.ceil(hits[0] + self.window - moment))
                return False, retry_after
            hits.append(moment)

            # Peer addresses cannot be supplied in request headers, but a
            # long-running public process can still see many of them. Retire
            # expired empty windows occasionally rather than growing forever.
            if len(self._hits) > 4096:
                stale = [peer for peer, seen in self._hits.items()
                         if not seen or seen[-1] <= cutoff]
                for peer in stale:
                    self._hits.pop(peer, None)
            return True, 0


BUNDLE_RATE_LIMITER = _BundleRateLimiter(
    BUNDLE_RATE_LIMIT, BUNDLE_RATE_WINDOW_SECONDS,
)

# Every endpoint that can start model, archive, or mutation work has a finite
# request envelope and process-local work budget.  These are safety nets for
# the small standard-library server, not a replacement for a trusted edge in a
# multi-process public deployment.  As with bundles, keys come only from the
# direct socket peer; caller-controlled forwarding headers are never read.
MAX_API_JSON_BYTES = 16 * 1024
MAX_QUESTION_CHARS = 1_000
MAX_IDENTIFIER_CHARS = 256
MAX_QUOTE_CHARS = 4_000
MAX_DECISION_BODY_CHARS = 4_000
MAX_FLAG_CLAIM_CHARS = 128
MAX_FLAG_REASON_CHARS = 400
MAX_SUBMIT_TEXT_CHARS = 400

MODEL_RATE_LIMITER = _BundleRateLimiter(limit=6, window=60.0)
ARCHIVE_RATE_LIMITER = _BundleRateLimiter(limit=20, window=60.0)
MUTATION_RATE_LIMITER = _BundleRateLimiter(limit=20, window=60.0)

MODEL_CONCURRENCY = 2
ARCHIVE_CONCURRENCY = 3
MODEL_BUSY_RETRY_SECONDS = 10
ARCHIVE_BUSY_RETRY_SECONDS = 5
MODEL_SLOTS = threading.BoundedSemaphore(MODEL_CONCURRENCY)
ARCHIVE_SLOTS = threading.BoundedSemaphore(ARCHIVE_CONCURRENCY)

POST_ONLY_ENDPOINTS = frozenset({
    "/api/ask", "/api/bundle", "/api/citation", "/api/decisions",
    "/api/flag", "/api/frontier", "/api/ledger", "/api/read",
    "/api/read/status", "/api/submit", "/api/watershed",
})

PUBLIC_STATIC_ASSETS = frozenset({"omega-portal.css", "portal-maplibre.js"})


def _bundle_resource_error(records: list[Any]) -> str | None:
    """Return why a parsed bundle exceeds the public verification budget.

    This pass touches only the already-decoded JSON. It runs before the rate
    allowance or verification semaphore is consumed and, most importantly,
    before an archive object is asked to fetch anything.
    """
    if len(records) > MAX_BUNDLE_RECORDS:
        return (
            f"bundle has {len(records)} records; maximum is "
            f"{MAX_BUNDLE_RECORDS}"
        )

    identifiers: set[str] = set()
    pages: set[tuple[str, int]] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            return f"record {index + 1} must be a JSON object"
        provenance = record.get("provenance") or {}
        if not isinstance(provenance, dict):
            return f"record {index + 1} provenance must be a JSON object"

        identifier = provenance.get("identifier")
        page = provenance.get("page")
        if identifier not in (None, ""):
            if not isinstance(identifier, str):
                return f"record {index + 1} identifier must be text"
            identifiers.add(identifier)
            if len(identifiers) > MAX_BUNDLE_IDENTIFIERS:
                return (
                    f"bundle cites more than {MAX_BUNDLE_IDENTIFIERS} unique "
                    "identifiers"
                )

        if page not in (None, "", 0):
            if isinstance(page, bool) or not isinstance(page, int) or page < 1:
                return f"record {index + 1} page must be a positive integer"
            if isinstance(identifier, str) and identifier:
                pages.add((identifier, page))
                if len(pages) > MAX_BUNDLE_PAGES:
                    return (
                        f"bundle cites more than {MAX_BUNDLE_PAGES} unique "
                        "identifier/page pairs"
                    )
    return None


def _origin_matches_host(origin: str, host: str) -> bool:
    """Return whether a browser Origin names this request's Host.

    ``Forwarded`` and ``X-Forwarded-*`` headers are intentionally irrelevant.
    A deployment behind a trusted proxy must perform its own host/origin policy
    at that edge; accepting caller-supplied forwarding metadata here would turn
    the CSRF check into an opt-out header.
    """
    if not origin or not host or "," in host:
        return False
    try:
        source = urlsplit(origin)
        target = urlsplit("//" + host)
        if source.scheme not in {"http", "https"}:
            return False
        if source.username is not None or source.password is not None:
            return False
        if target.username is not None or target.password is not None:
            return False
        if source.path not in {"", "/"} or source.query or source.fragment:
            return False
        if target.path or target.query or target.fragment:
            return False
        source_host = (source.hostname or "").rstrip(".").casefold()
        target_host = (target.hostname or "").rstrip(".").casefold()
        if not source_host or source_host != target_host:
            return False
        default_port = 443 if source.scheme == "https" else 80
        return (source.port or default_port) == (target.port or default_port)
    except ValueError:
        return False


def _host_parts(value: str) -> tuple[str, int | None] | None:
    if not value or "," in value:
        return None
    try:
        parsed = urlsplit("//" + value)
        if (parsed.username is not None or parsed.password is not None or
                parsed.path or parsed.query or parsed.fragment):
            return None
        hostname = (parsed.hostname or "").rstrip(".").casefold()
        if not hostname:
            return None
        return hostname, parsed.port
    except ValueError:
        return None


def _request_host_allowed(host: str) -> bool:
    """Reject DNS-rebinding Host values unless explicitly configured.

    The default server binds loopback, so only loopback names are trusted by
    default. A reverse-proxied public deployment must set the comma-separated
    ``CONCORDANCE_PUBLIC_HOSTS`` value to its exact Host name (and port when the
    browser includes one).
    """
    actual = _host_parts(host)
    if actual is None:
        return False
    hostname, _port = actual
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        return True
    configured = os.environ.get("CONCORDANCE_PUBLIC_HOSTS", "")
    return actual in {
        parsed
        for entry in configured.split(",")
        if (parsed := _host_parts(entry.strip())) is not None
    }


class _ApiInputError(ValueError):
    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _text_field(
    payload: dict[str, Any],
    name: str,
    limit: int,
    *,
    strip: bool = True,
) -> str:
    value = payload.get(name, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise _ApiInputError(f"{name} must be text")
    if len(value) > limit:
        raise _ApiInputError(
            f"{name} exceeds the {limit}-character limit", status=413,
        )
    return value.strip() if strip else value

# Reading a missing place invokes archive fetches and a local model and can run
# for hours. It is not a safe GET action: crawlers, link previews and browser
# prefetch may issue GETs without a person choosing the work. Keep the future
# browser-to-local handoff visible as unfinished rather than running that job on
# the public server by accident.
REMOTE_READ_DISABLED = (
    "server-side reading is disabled; run the local reader and submit a "
    "verified bundle instead"
)

#: Suffixes that turn a town's name into a facility's. Stripped only when
#: deciding WHICH TOWN a record belongs to; the facility itself stays on the
#: record, because a town's sewage plant and its water works measure opposite
#: things and must never share a chart.
#: Written without a word-boundary escape on purpose. This pattern was authored
#: through a shell heredoc and every `\b` in it became a literal backspace byte
#: -- the file read back correctly in every editor and the pattern matched
#: nothing, so "Owen Sound Sewage Treatment Plant" failed to resolve to "Owen
#: Sound" and the flagship trend stayed broken after being fixed. The repo-wide
#: control-byte test caught it; removing the construct removes the trap.
_FACILITY_SUFFIX = re.compile(
    r"(?i)\s+(water pollution control plant|sewage treatment plant|"
    r"pollution control plant|water treatment plant|water supply system|"
    r"treatment plant|filtration plant|sewage works|water works|"
    r"wpcp|stp|wtp|plant|works)(?![a-z]).*$")


def _same_town(place: str, want: set[str]) -> bool:
    """Is this record about one of the towns asked for?

    A record's place is whatever its sentence said, so one town arrives under
    several spellings. Owen Sound's BOD removal sits under "Owen Sound" for two
    years and "Owen Sound Sewage Treatment Plant" for a third -- and the third
    is the 46.4% that both the README and the application quote as the start of
    the series.
    """
    if not place:
        return False
    if place in want:
        return True
    bare = _FACILITY_SUFFIX.sub("", place).strip(" ,-")
    return bool(bare) and bare in want


def _load_public_corpus() -> Corpus:
    """Load extraction and accepted individual contributions as one corpus.

    Contribution files deliberately live outside ``data/results`` so their
    authorship remains visible on disk.  That storage distinction must not
    leak into the public data model: once archive verification accepted a
    reading, the library, charts, and Jay should all see it.  Record identity
    is recomputed from content and used here to avoid publishing the same
    reading twice when it already exists in an extraction or another accepted
    contribution.
    """
    extracted = Corpus.load_dir(RESULTS)
    contribution_paths = sorted(CONTRIBUTIONS.glob("*.json"))
    contributed = Corpus.load(*contribution_paths)

    records = []
    seen: set[str] = set()
    for record in [*extracted.records, *contributed.records]:
        identity = public_record_key(record.to_dict())
        if identity in seen:
            continue
        seen.add(identity)
        records.append(record)

    places = list(extracted.places)
    for record in records:
        if record.place and record.place not in places:
            places.append(record.place)
    return Corpus(records=records, places=places)


def _load_public_claims() -> list[Any]:
    """Load each evidence claim once across extraction and contribution stores."""
    return load_public_claims(
        RESULTS, CONTRIBUTIONS, RESULTS / "vision_trial_corpus.json",
    )


class State:
    """Everything the server can answer from, loaded once at startup."""

    def __init__(self) -> None:
        self.silence = self._read("silence_report.json")
        self.census = self._read("corpus_census.json")
        self.gold = self._read("gold_report.json")
        self.archive = Archive()
        self._collection_identifiers = frozenset(
            str(item.get("identifier"))
            for item in self.archive.load_index()
            if isinstance(item, dict) and item.get("identifier")
        )
        self._reload_lock = threading.Lock()
        # Durable contribution writes and the in-memory library are two
        # separate commits.  Generations keep a failed second commit pending so
        # an idempotent retry can publish an already-present file.  A boolean is
        # insufficient: a second write can land while an earlier reload is in
        # flight, and that newer write must remain pending even if the older
        # snapshot publishes successfully.
        self._publication_lock = threading.Lock()
        self._durable_generation = 0
        self._published_generation = 0
        # These are non-blocking single-flight gates, not ordinary cache locks.
        # A second HTTP request for the same cold view gets a quick busy reply
        # instead of occupying another shared archive worker while it waits.
        self._ledger_lock = threading.Lock()
        self._frontier_lock = threading.Lock()
        self._watershed_lock = threading.Lock()
        self._ledger_base: dict[str, Any] | None = None
        self._ledger_claim_slots: dict[str, str] = {}
        self._ledger_slot_meta: dict[str, dict[str, Any]] = {}
        self._frontier: dict[str, Any] | None = None
        self._watershed: dict[str, Any] | None = None
        self._links: list[Any] = []
        self._claims: list[Any] = []
        self._known_claim_ids: set[str] = set()
        self.corpus = Corpus(records=[], places=[])
        self.places: list[dict[str, Any]] = []
        self.jay: Jay
        self.reload()

    def invalidate_ledger(self) -> None:
        """Invalidate evidence derived from a changed record collection.

        Flags intentionally do not call this. Their only effect is a cheap
        overlay over already-resolved evidence, so an inert or nonexistent
        objection can never force the archive-wide verification pass to run
        again.
        """
        with self._ledger_lock:
            self._ledger_base = None
            self._ledger_claim_slots = {}
            self._ledger_slot_meta = {}
        with self._frontier_lock:
            self._frontier = None

    def has_claim(self, claim_id: str) -> bool:
        return claim_id in self._known_claim_ids

    def allows_archive_identifier(self, identifier: str) -> bool:
        """Whether public work may fetch this configured-collection item."""
        return identifier in self._collection_identifiers

    def evidence_cached(self, view: str) -> bool:
        if view == "ledger":
            return self._ledger_base is not None
        if view == "frontier":
            return self._frontier is not None
        if view == "watershed":
            return self._watershed is not None
        raise ValueError(f"unknown evidence view: {view}")

    def evidence_build_lock(self, view: str) -> threading.Lock:
        if view == "ledger":
            return self._ledger_lock
        if view == "frontier":
            return self._frontier_lock
        if view == "watershed":
            return self._watershed_lock
        raise ValueError(f"unknown evidence view: {view}")

    def frontier(self) -> dict[str, Any]:
        """Questions the archive is one document away from answering.

        Cached alongside the ledger: it reads every extraction on disk and the
        silence report, and the answer only changes when something is read.
        """
        if self._frontier is not None:
            return self._frontier  # type: ignore[return-value]

        # Only one first request builds this cache. Public request concurrency
        # is bounded outside State, while this lock prevents the admitted
        # requests from repeating the same ECCC/archive work in parallel.
        with self._frontier_lock:
            if self._frontier is not None:
                return self._frontier
            self._frontier = self._build_frontier()
            return self._frontier

    def _build_frontier(self) -> dict[str, Any]:
        """Build the flag-independent frontier while holding its cache lock."""

        # River questions need the watershed, which is a network call. If it
        # is unavailable the frontier still answers -- trends, silences and the
        # decisions behind a town's numbers need no gauges -- and says so
        # rather than failing whole.
        try:
            self.watershed()
        except Exception:  # noqa: BLE001
            pass
        links = getattr(self, "_links", None) or []

        try:
            f = load_frontier(downstream_links=links)
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)[:160], "waiting": [], "places": []}

        return {
            "answerable": [q.to_dict() for q in f.answerable[:20]],
            "waiting": [q.to_dict() for q in f.waiting[:40]],
            "places": f.ranked_places(15),
            "counts": {
                "answerable": len(f.answerable),
                "waiting": len(f.questions) - len(f.answerable),
                "places_read": len(f.read_places),
                "rivers_available": bool(links),
            },
        }

    def ledger(self) -> dict[str, Any]:
        """Every claim's standing, with page links and crops when available."""
        with self._ledger_lock:
            if self._ledger_base is None:
                self._build_ledger_base()
        return self._ledger_report()

    def _ledger_report(self) -> dict[str, Any]:
        """Apply cheap flag state to an already-built evidence ledger."""
        base = dict(self._ledger_base or {})
        claim_slots = dict(self._ledger_claim_slots)
        slot_meta = dict(self._ledger_slot_meta)

        # Flags have no evidence and cannot change a standing. Attach them to a
        # copy of the cached evidence report instead of feeding them back into
        # archive resolution. This makes their effect immediate and cheap while
        # making invalid claim IDs inert.
        with FLAGS_LOCK:
            current_flags = list(FLAGS)
        flags_by_slot: dict[str, list[Flag]] = {}
        for flag in current_flags:
            slot_key = claim_slots.get(flag.claim_id)
            if slot_key is not None:
                flags_by_slot.setdefault(slot_key, []).append(flag)

        base["flags"] = sum(len(items) for items in flags_by_slot.values())
        ranked = sorted(
            flags_by_slot.items(), key=lambda item: (-len(item[1]), item[0]),
        )
        base["most_flagged"] = [
            {
                "slot": slot_key,
                "flags": len(items),
                "state": slot_meta[slot_key]["state"],
                "values": slot_meta[slot_key]["values"],
                "reasons": [flag.reason[:120] for flag in items[:4]],
            }
            for slot_key, items in ranked[:20]
            if slot_key in slot_meta
        ]
        base["contested_detail"] = [
            {
                **detail,
                "n_flags": len(flags_by_slot.get(str(detail.get("slot")), [])),
            }
            for detail in base.get("contested_detail", [])
        ]
        return base

    def build_evidence_view(self, view: str) -> dict[str, Any]:
        """Build one cold evidence view while its single-flight gate is held."""
        if view == "ledger":
            if self._ledger_base is None:
                self._build_ledger_base()
            return self._ledger_report()
        if view == "frontier":
            if self._frontier is None:
                self._frontier = self._build_frontier()
            return self._frontier
        if view == "watershed":
            if self._watershed is None:
                self._watershed = self._build_watershed()
            return self._watershed
        raise ValueError(f"unknown evidence view: {view}")

    def _build_ledger_base(self) -> None:
        """Resolve evidence once; caller holds ``_ledger_lock``."""
        # The machine's readings and people's submissions go in together, on
        # the same footing. Nothing downstream can tell which is which,
        # because nothing downstream is allowed to care. Flags are overlaid
        # later because they cannot affect evidence standing.
        resolved = resolve_claims(self._claims, archive=self.archive)
        report = resolved.report()

        claim_slots: dict[str, str] = {}
        slot_meta: dict[str, dict[str, Any]] = {}
        for slot in resolved.slots.values():
            slot_meta[slot.key] = {"state": slot.state, "values": slot.values}
            for standing in slot.standings:
                claim_slots[standing.claim.id] = slot.key

        contested = []
        for slot in resolved.contested()[:40]:
            entries = []
            for standing in slot.surviving:
                prov = standing.claim.record.get("provenance") or {}
                entry = standing.to_dict()
                entry["claim_id"] = standing.claim.id
                entry["page_url"] = ""
                entry["crop_url"] = ""
                try:
                    page = {p.page: p for p in self.archive.pages(
                        str(prov.get("identifier")), with_words=True)}[prov.get("page")]
                    citation = cite_record(page, standing.claim.record)
                    entry["crop_url"] = citation.crop_url
                    entry["page_url"] = citation.page_url
                    entry["citation_kind"] = citation.kind
                except Exception:  # noqa: BLE001
                    pass
                entries.append(entry)
            contested.append({
                "slot": slot.key, "values": slot.values,
                "same_sentence": slot.same_sentence,
                "n_flags": 0,
                "readings": entries,
            })

        report["contested_detail"] = contested
        self._ledger_base = report
        self._ledger_claim_slots = claim_slots
        self._ledger_slot_meta = slot_meta

    @staticmethod
    def _read(name: str) -> dict[str, Any]:
        p = RESULTS / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def _geocode(self, corpus: Corpus | None = None) -> list[dict[str, Any]]:
        try:
            from .places import resolve
        except Exception:  # noqa: BLE001
            return []
        active_corpus = corpus or self.corpus
        have = {(r.place or "").lower() for r in active_corpus.records}
        out = []
        for m in self.silence.get("municipalities", []):
            p = resolve(m["place"], m.get("last_year") or 1970)
            lat, lon = getattr(p, "lat", None), getattr(p, "lon", None)
            if not (p and lat and lon):
                continue
            out.append({
                "place": p.canonical,
                "raw": m["place"],
                "lat": lat,
                "lon": lon,
                "first": m["first_year"],
                "last": m["last_year"],
                "years": len(m["reported_years"]),
                "reported": m["reported_years"],
                "silent_since": m.get("silent_since"),
                "extracted": p.canonical.lower() in have or m["place"].lower() in have,
            })
        return out


    # -- what the portal asks for -----------------------------------------

    def mark_reload_needed(self) -> int:
        """Record one completed durable write and return its generation."""
        with self._publication_lock:
            self._durable_generation += 1
            return self._durable_generation

    @property
    def reload_needed(self) -> bool:
        """Whether disk contains a write not yet committed to live state."""
        with self._publication_lock:
            return self._published_generation < self._durable_generation

    def _reload_generation(self, generation: int) -> None:
        """Build and publish one snapshot while ``_reload_lock`` is held."""
        corpus = _load_public_corpus()
        claims = _load_public_claims()
        places = self._geocode(corpus)
        jay = Jay(corpus)

        self.corpus = corpus
        self._claims = claims
        self._known_claim_ids = {claim.id for claim in claims}
        self.places = places
        self.jay = jay
        self.invalidate_ledger()
        with self._publication_lock:
            # Never claim a write newer than the snapshot target. A concurrent
            # contribution may have landed while the files were being read; it
            # remains pending and causes a later reload (possibly redundant,
            # but always conservative).
            self._published_generation = max(
                self._published_generation, generation,
            )

    def reload_if_needed(self) -> bool:
        """Publish pending durable writes; leave them pending on any failure."""
        with self._reload_lock:
            with self._publication_lock:
                generation = self._durable_generation
                if self._published_generation >= generation:
                    return False
            self._reload_generation(generation)
            return True

    def reload(self) -> None:
        """Re-read every accepted record and atomically rebind query tools."""
        with self._reload_lock:
            with self._publication_lock:
                generation = self._durable_generation
            self._reload_generation(generation)

    def html(self) -> str:
        totals = self.gold.get("totals", {})
        stop = self.silence.get("largest_simultaneous_stop", {})
        return render({
            "corpus_items": self.census.get("extrapolation", {}).get("corpus_items", 104241),
            "located": len(self.places),
            "read": sum(1 for p in self.places if p["extracted"]),
            "records": len(self.corpus.records),
            "precision": totals.get("precision", 0.0),
            "silent_n": stop.get("municipalities", "—"),
            "silent_year": stop.get("year", "—"),
        })

    def watershed(self) -> dict[str, Any]:
        """Who was downstream of whom, plus what the method refused to link.

        Cached on first request: it needs the Water Survey gauge list, which is
        a network call, and the answer does not change between requests.
        """
        if self._watershed is not None:
            return self._watershed  # type: ignore[return-value]

        with self._watershed_lock:
            if self._watershed is not None:
                return self._watershed
            self._watershed = self._build_watershed()
            return self._watershed

    def _build_watershed(self) -> dict[str, Any]:
        """Build the ECCC-derived view while holding its cache lock."""

        out: dict[str, Any] = {"rivers": [], "warnings": [], "error": None}
        try:
            from .places import resolve
            from .providers import Fetcher, Registry
            from .watershed import downstream_links, load_stations, place_plants

            reg, fetch = Registry.load(), Fetcher()
            geo = fetch.fetch(reg.providers["eccc-hydrometric-stations"],
                              {"PROV_TERR_STATE_LOC": "ON", "limit": "3000", "f": "json"})
            stations = load_stations(geo)
            plants = []
            for m in self.silence.get("municipalities", []):
                p = resolve(m["place"], m.get("last_year") or 1970)
                if p and getattr(p, "lat", None) and getattr(p, "lon", None):
                    plants.append((p.canonical, p.lat, p.lon))
            links, warnings = downstream_links(place_plants(plants, stations))
            # Kept as the objects rather than the serialised rivers: the
            # frontier needs upstream/downstream/watercourse, and rebuilding
            # them from the JSON would be a second definition to keep in step.
            self._links = links

            rivers: dict[str, list[dict[str, Any]]] = {}
            for link in links:
                rivers.setdefault(link.watercourse, []).append({
                    "upstream": link.upstream, "downstream": link.downstream,
                    "up_area": link.upstream_drainage_km2,
                    "down_area": link.downstream_drainage_km2,
                    "confidence": link.confidence,
                })
            out["rivers"] = [{"river": r, "links": ls} for r, ls in sorted(rivers.items())]
            out["warnings"] = warnings
            out["caveat"] = links[0].caveat if links else ""
        except Exception as exc:  # noqa: BLE001
            out["error"] = str(exc)[:200]

        return out

    def geojson(self) -> dict[str, Any]:
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
                    "properties": {
                        "place": p["place"], "raw": p["raw"], "years": p["years"],
                        "first": p["first"], "last": p["last"],
                        "silent_since": p["silent_since"] or "",
                        "extracted": p["extracted"],
                        # The actual years this place filed, so the timeline can
                        # show who was reporting in a given year rather than just
                        # who ever reported.
                        "reported": p.get("reported", []),
                    },
                }
                for p in self.places
            ],
        }

    #: Parameters promoted to the top of a place page when they are present.
    #: NOT a filter -- everything a place measured is shown, discovered from its
    #: own records. This list only decides what a non-specialist sees first,
    #: because "how much did the plant take out" reads more easily than
    #: "mixed liquor suspended solids".
    #:
    #: It used to BE the filter, and that was the bug behind "I wondered how
    #: useful the data actually is being presented this way". Seven water
    #: parameters decided what existed, so Stratford showed 4 charts out of 66
    #: distinct measurements and Richmond Hill 4 out of 60. Roughly three
    #: quarters of everything read was never rendered at all: an archive-wide
    #: reader with a water-report viewer bolted to the front of it.
    PREFERRED = [
        "BOD removal", "suspended solids removal", "BOD",
        "suspended solids", "daily flow", "total flow", "population",
    ]

    def town(self, place: str, raw: str) -> dict[str, Any]:
        out = find_my_town(self.corpus, place)
        if not out.get("found") and raw:
            out = find_my_town(self.corpus, raw)
        if not out.get("found"):
            return out

        # Match the town, not the exact string. One town's records carry several
        # place spellings because the extractor takes the place from whatever
        # the sentence said: Owen Sound's BOD-removal series is filed under
        # "Owen Sound" for 1963 and 1969 and under "Owen Sound Sewage Treatment
        # Plant" for the 1963 reading of 46.4%. Exact matching therefore dropped
        # the very number both the README and the application lead with, and the
        # live portal drew a flat line where a rising one exists.
        #
        # This is a place question, so the facility suffix is noise -- and it is
        # NOT dropped from the records, because the facility split below is what
        # keeps a town's sewage plant off the same panel as its water works.
        want = {p for p in (place.lower(), raw.lower()) if p}
        mine = [r for r in self.corpus.records
                if r.kind == "observation" and _same_town((r.place or "").lower(), want)]
        # Effluent and tap water are opposite measurements and must never share
        # a panel -- but the fix for that used to be dropping every facility
        # except the largest, which threw away most of a town's record. Belleville
        # carries 26 distinct facility strings; keeping only the commonest left
        # a panel that answered almost nothing.
        #
        # So the facility is carried INTO the series identity instead of used to
        # discard. Nothing is merged that should not be, and nothing is lost.
        facilities = Counter(r.facility or "unclassified" for r in mine)
        out["facility"] = facilities.most_common(1)[0][0] if facilities else ""
        out["facilities"] = [{"name": f, "n": n} for f, n in facilities.most_common()]

        # What did this place actually measure? Ask the records, do not consult
        # a list written when the corpus was one town's sewage reports.
        # A PARTITION: every record lands in exactly one group. Re-filtering by
        # parameter name inside series_from_records instead put records in more
        # than one series -- "BOD" matches "BOD removal" by substring -- and the
        # page then showed 103.7% of the town's observations, which is how a
        # duplicate announces itself if you happen to count.
        found: dict[tuple[str, str | None, str], list[Any]] = {}
        for r in mine:
            got = resolve_parameter(
                r.parameter, r.unit,
                context=(r.provenance.source_text if r.provenance else None))
            label = got.label if got else (r.parameter or "").strip()
            if not label:
                continue
            found.setdefault((label, r.stream, r.facility or "unclassified"),
                             []).append(r)

        def rank(item: tuple[tuple[str, str | None, str], list[Any]]) -> tuple[int, int, int]:
            (label, _stream, facility), group = item
            n = len(group)
            pref = next((i for i, w in enumerate(self.PREFERRED)
                         if w.lower() in label.lower()), len(self.PREFERRED))
            main = 0 if facility == out["facility"] else 1
            return (main, pref, -n)

        series = []
        singles = []
        # Deduplicate across the WHOLE place, not per group. A reading can land
        # in two groups when its stream or facility differs between extractions,
        # and a per-group set then lets the same page/value/unit through twice --
        # 72 of Belleville's 475 rows.
        seen_rows: set[tuple[Any, ...]] = set()
        for (label, stream, facility), group in sorted(found.items(), key=rank):
            # Only this group's records, so nothing can be claimed twice.
            s = series_from_records(group, parameter=label, stream=stream)
            # A group that cannot form a comparable series -- mixed units, an
            # unrecognised unit, one unusable period -- still HAPPENED, and its
            # readings still cite pages. Dropping it was the last place a
            # town's record silently shrank.
            if not s.points:
                bare = _bare_group(label, stream, facility, group,
                                   out.get("facility", ""), seen_rows)
                if bare["rows"]:
                    singles.append(bare)
                continue
            # EVERY reading in this group, not one per year.
            #
            # The chart keeps the most confident reading per year, which is
            # right for a line and wrong for a table: a parameter measured
            # monthly showed one point and hid eleven readings, and those
            # readings are the actual answer to "what was measured here".
            # Charting one and listing all is the honest split -- and the
            # charted year is marked, so the table says which number the line
            # is drawn through.
            charted = {int(y): (s.sources.get(y), v) for y, v, _c in s.points}
            rows = []
            for r in sorted(group, key=lambda r: (str(r.period or ""), str(r.parameter))):
                # The same reading extracted twice from one page is one reading.
                prov0 = r.provenance
                # The label matters: "BOD 12 mg/L" and "suspended solids
                # 12 mg/L" on one page are two readings, and a key without it
                # silently merged them.
                dedupe = (label, prov0.identifier if prov0 else "",
                          prov0.page if prov0 else 0,
                          r.value, r.unit, str(r.period), r.qualifier)
                if dedupe in seen_rows:
                    continue
                seen_rows.add(dedupe)
                prov = r.provenance
                try:
                    year = int(str(r.period)[:4])
                except (TypeError, ValueError):
                    year = None
                src, cv = charted.get(year, (None, None))
                rows.append({
                    # The period the page states, not just its year. Three
                    # monthly readings all rendered "1969" and looked like the
                    # same row repeated three times with different numbers,
                    # which reads as a bug and is actually the data.
                    "period": str(r.period) if r.period else "",
                    "year": year if year is not None else "",
                    "parameter": label,
                    "value": f"{r.value:.4g}" if isinstance(r.value, (int, float)) else "",
                    "unit": r.unit or s.unit,
                    "qualifier": r.qualifier or "",
                    # True for the reading the line actually passes through.
                    "charted": bool(src is not None and src is r),
                    "read_from": (prov.source_text[:150] if prov else ""),
                    "page_url": (prov.page_url if prov else ""),
                    # Enough for the portal to ask /api/citation for a picture of
                    # this exact sentence. The quote is sent whole rather than
                    # truncated, because the crop is found by matching its words
                    # against the page's OCR and 150 characters is not always a
                    # sentence.
                    "identifier": (prov.identifier if prov else ""),
                    "page": (prov.page if prov else 0),
                    "quote": (prov.source_text if prov else ""),
                })
            entry = {
                "label": label, "unit": s.unit,
                # Only shown when a town has more than one, so a single-plant
                # town is not made to look complicated.
                "facility": "" if facility == out["facility"] else facility,
                "stream": stream or "",
                "points": [[int(y), v] for y, v, _ in s.points],
                "rows": rows,
            }
            # One reading is a fact, not a trend, and belongs in the inventory
            # rather than on a chart. It used to be dropped entirely, which is
            # how most of a town's record became invisible.
            (series if len(s.points) > 1 else singles).append(entry)

        out["series"] = series
        out["singles"] = singles
        out["n_charted"] = sum(len(e["points"]) for e in series)
        out["n_listed"] = len(singles)
        return out


def _bare_group(label: str, stream: str | None, facility: str,
                group: list[Any], main_facility: str,
                seen: set[tuple[Any, ...]]) -> dict[str, Any]:
    """Readings that cannot be charted, listed rather than lost.

    A series needs comparable units and at least one usable period. When a
    group has neither, the readings are still real and still cite pages, so
    they belong on the page with everything else -- flagged, not hidden.
    """
    rows = []
    for r in group:
        prov = r.provenance
        key = (label, prov.identifier if prov else "", prov.page if prov else 0,
               r.value, r.unit, str(r.period), r.qualifier)
        if key in seen:
            continue
        seen.add(key)
        try:
            year: Any = int(str(r.period)[:4])
        except (TypeError, ValueError):
            year = ""
        rows.append({
            "period": str(r.period) if r.period else "", "year": year,
            "parameter": label,
            "value": f"{r.value:.4g}" if isinstance(r.value, (int, float)) else "",
            "unit": r.unit or "", "qualifier": r.qualifier or "", "charted": False,
            "read_from": (prov.source_text[:150] if prov else ""),
            "page_url": (prov.page_url if prov else ""),
            "identifier": (prov.identifier if prov else ""),
            "page": (prov.page if prov else 0),
            "quote": (prov.source_text if prov else ""),
        })
    return {"label": label, "unit": "", "stream": stream or "",
            "facility": "" if facility == main_facility else facility,
            "points": [], "rows": rows, "not_comparable": True}


STATE: State | None = None


def _mark_publication_pending(state: Any) -> None:
    """Mark a durable write, with a small fallback for lightweight test states."""
    marker = getattr(state, "mark_reload_needed", None)
    if callable(marker):
        marker()
        return
    # Endpoint tests and small embedders sometimes provide only ``reload``.
    # Keeping the fallback state-local preserves the same retry semantics
    # without weakening the generation-safe implementation used by State.
    setattr(state, "_reload_needed", True)


def _refresh_publication(state: Any, *, wrote: bool) -> tuple[bool, str]:
    """Publish a durable write or an earlier pending one.

    The returned boolean reports whether the live corpus is current for this
    request. The error is deliberately bounded before it reaches public JSON.
    A failed reload never clears the pending marker, so replay can try again.
    """
    if wrote:
        _mark_publication_pending(state)
    try:
        refresh = getattr(state, "reload_if_needed", None)
        if callable(refresh):
            refresh()
        elif getattr(state, "_reload_needed", False):
            state.reload()
            setattr(state, "_reload_needed", False)
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).strip() or type(exc).__name__
        return False, detail[:160]
    return True, ""


def _public_identifiers(records: list[Any]) -> set[str]:
    out: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        provenance = record.get("provenance")
        if isinstance(provenance, dict) and provenance.get("identifier"):
            out.add(str(provenance["identifier"]))
    return out


class Handler(BaseHTTPRequestHandler):
    def _send(
        self,
        body: bytes,
        ctype: str,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(
        self,
        payload: dict[str, Any],
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._send(
            json.dumps(payload).encode(), "application/json",
            status=status, headers=headers,
        )

    def _direct_peer(self) -> str:
        return str(self.client_address[0]) if self.client_address else "unknown"

    def _archive_identifier_allowed(self, identifier: str) -> bool:
        """Apply the live collection boundary (test doubles may omit it)."""
        assert STATE is not None
        check = getattr(STATE, "allows_archive_identifier", None)
        return bool(check(identifier)) if callable(check) else True

    def _method_not_allowed(self, allow: str) -> None:
        self._send_json(
            {"error": f"method not allowed; use {allow}"},
            status=405, headers={"Allow": allow},
        )

    def _read_json(self, max_bytes: int) -> tuple[bool, Any]:
        """Read one bounded same-origin JSON request body.

        An absent Origin is accepted for command-line and other non-browser
        clients.  When a browser supplies one, it must match the actual Host
        header; forwarding headers cannot influence the decision.
        """
        media_type = (self.headers.get("Content-Type") or "").split(";", 1)[0]
        if media_type.strip().casefold() != "application/json":
            self._send_json(
                {"error": "Content-Type must be application/json"}, status=415,
            )
            return False, None

        origin = (self.headers.get("Origin") or "").strip()
        host = (self.headers.get("Host") or "").strip()
        if not _request_host_allowed(host):
            self._send_json(
                {"error": "request Host is not trusted by this instance"}, status=403,
            )
            return False, None
        if origin and not _origin_matches_host(origin, host):
            self._send_json(
                {"error": "request Origin does not match Host"}, status=403,
            )
            return False, None

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            length = 0
        if length <= 0:
            self._send_json({"error": "a non-empty JSON body is required"}, status=400)
            return False, None
        if length > max_bytes:
            self._send_json(
                {"error": f"request body exceeds {max_bytes} bytes"}, status=413,
            )
            return False, None

        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("request body ended early")
            return True, json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            self._send_json(
                {"error": f"not readable as JSON: {str(exc)[:120]}"}, status=400,
            )
            return False, None

    def _rate_allowed(self, limiter: _BundleRateLimiter, label: str) -> bool:
        allowed, retry_after = limiter.check(self._direct_peer())
        if allowed:
            return True
        self._send_json(
            {
                "error": f"too many {label} requests; try again later",
                "retry_after": retry_after,
            },
            status=429, headers={"Retry-After": str(retry_after)},
        )
        return False

    # -- receiving readings from other machines ---------------------------

    def do_POST(self) -> None:  # noqa: N802
        """Run bounded JSON-only work that is unsafe or expensive as GET.

        Browsers cannot smuggle any of these through a cross-site form because
        text/plain and form encodings are refused, and a supplied Origin must
        name this Host.  Non-browser clients may omit Origin but must still use
        JSON and are subject to the same direct-peer work budgets.
        """
        assert STATE is not None
        path = urlparse(self.path).path
        if path not in POST_ONLY_ENDPOINTS:
            self.send_error(404)
            return

        max_bytes = MAX_BUNDLE_BYTES if path == "/api/bundle" else MAX_API_JSON_BYTES
        ok, payload = self._read_json(max_bytes)
        if not ok:
            return
        if not isinstance(payload, dict):
            self._send_json({"error": "JSON body must be an object"}, status=400)
            return

        dispatch = {
            "/api/ask": self._post_ask,
            "/api/bundle": self._post_bundle,
            "/api/citation": self._post_citation,
            "/api/decisions": self._post_decisions,
            "/api/flag": self._post_flag,
            "/api/frontier": self._post_frontier,
            "/api/ledger": self._post_ledger,
            "/api/read": self._post_read,
            "/api/read/status": self._post_read_status,
            "/api/submit": self._post_submit,
            "/api/watershed": self._post_watershed,
        }
        dispatch[path](payload)

    # -- reading a place on demand -----------------------------------------

    def _is_local_instance(self) -> bool:
        """Is this the asker's own machine, rather than somebody's server?

        Reading a town is hours of local model time. Offering that from a
        public host hands every visitor a lever on somebody else's graphics
        card, so it is refused there -- but on the machine in front of you, the
        reader IS your machine, which is the whole design.

        Both halves are required: the peer must be loopback AND no public host
        may be configured, so a reverse-proxied deployment cannot be talked
        into enabling it by a forged Host header.
        """
        peer = (self._direct_peer() or "").strip()
        loopback = peer in {"127.0.0.1", "::1", "localhost"}
        public = os.environ.get("CONCORDANCE_PUBLIC_HOSTS", "").strip()
        return loopback and not public

    def _post_read(self, payload: dict[str, Any]) -> None:
        """Read a place nobody has read yet, here, now."""
        if not self._is_local_instance():
            self._send_json({
                "error": REMOTE_READ_DISABLED,
                "local_reader": (
                    "python scripts/extract_place.py --place PLACE "
                    "--title-filter PLACE"
                ),
            }, status=501)
            return

        place = _text_field(payload, "place", 120)
        raw = _text_field(payload, "raw", 120)
        if not place:
            self._send_json({"error": "no place given"}, status=400)
            return

        from .library import ask as _ask

        started, job = READER.start(
            place, raw, ask=_ask,
            after=_mark_publication_pending and (lambda: _mark_publication_pending(STATE)),
        )
        self._send_json({
            "started": started,
            "busy": not started,
            "job": job.to_dict(),
            "note": ("Reading on this machine. It takes roughly a minute a page, "
                     "so a town is usually an hour or two. You can leave; the "
                     "result is kept and everybody who asks after you gets it "
                     "immediately.")
            if started else
            ("Already reading %s. There is one graphics card, so this waits "
             "rather than queues." % job.place),
        }, status=200 if started else 409)

    def _post_read_status(self, payload: dict[str, Any]) -> None:
        """Where the current read has got to."""
        if not self._is_local_instance():
            self._send_json({"error": REMOTE_READ_DISABLED}, status=501)
            return
        job = READER.current
        self._send_json({
            "reading": READER.busy(),
            "job": job.to_dict() if job else None,
        })

    def _post_bundle(self, bundle: dict[str, Any]) -> None:
        """Accept a bundle of readings from somebody else's machine.

        This is the destination the distributed model was missing. Until it
        existed, `library.ask` read a town on your laptop and `share.py export`
        packaged it, and there the trail went cold -- "your machine reads it for
        everyone" had nowhere to send the result.

        Nothing about the sender is examined and no account is required, because
        nothing about the sender is relevant. Prose evidence is re-verified
        against archive.org: the quoted span must be on that page and contain
        the complete value token. Locator-only table evidence is examined but
        remains unsupported without localized cell proof. A bundle from a
        stranger and one from the maintainer are handled identically.

        The instance is a convenience, not an authority. It holds no key that
        anyone else lacks, and anyone who mistrusts it can pull the dataset,
        re-evaluate each record's cited evidence, and run their own -- which is
        the property that stops a shared server becoming a single point of trust.
        """
        assert STATE is not None
        records = bundle.get("records")
        if not isinstance(records, list) or not records:
            self._send(json.dumps({
                "accepted": False,
                "why": "no records in the bundle",
            }).encode(), "application/json")
            return

        resource_error = _bundle_resource_error(records)
        if resource_error:
            self._send(json.dumps({
                "accepted": False,
                "why": resource_error,
                "limits": {
                    "records": MAX_BUNDLE_RECORDS,
                    "identifiers": MAX_BUNDLE_IDENTIFIERS,
                    "identifier_pages": MAX_BUNDLE_PAGES,
                },
            }).encode(), "application/json", status=413)
            return
        unknown = sorted(
            identifier for identifier in _public_identifiers(records)
            if not self._archive_identifier_allowed(identifier)
        )
        if unknown:
            self._send_json(
                {
                    "accepted": False,
                    "why": "bundle cites an item outside the configured collection",
                    "identifier": unknown[0],
                },
                status=400,
            )
            return

        # Use the socket peer only. X-Forwarded-For and similar headers are
        # caller-controlled unless a particular trusted proxy has sanitized
        # them, which this small standard-library server cannot establish.
        peer = str(self.client_address[0]) if self.client_address else "unknown"
        allowed, retry_after = BUNDLE_RATE_LIMITER.check(peer)
        if not allowed:
            self._send(json.dumps({
                "accepted": False,
                "why": "too many bundle submissions; try again later",
                "retry_after": retry_after,
            }).encode(), "application/json", status=429,
                headers={"Retry-After": str(retry_after)})
            return

        if not BUNDLE_VERIFY_SLOTS.acquire(blocking=False):
            retry_after = BUNDLE_BUSY_RETRY_SECONDS
            self._send(json.dumps({
                "accepted": False,
                "why": "bundle verification is busy; try again later",
                "retry_after": retry_after,
            }).encode(), "application/json", status=503,
                headers={"Retry-After": str(retry_after)})
            return

        try:
            verdict = verify_bundle(bundle, archive=STATE.archive)

            # Keep what the archive supports and report the rest, rather than
            # refusing the whole bundle over one unverifiable reading. Every
            # record's standing is individually known and the ledger has a state
            # for "unsupported", so what is left out is a reported absence.
            # ``verify_bundle`` is the one authority on which exact records the
            # archive supported. Reconstructing that set by subtracting only
            # `failed` silently kept `unsupported` records whose pages or quotes
            # could not be checked. Use the verifier's positive set instead.
            supported = getattr(verdict, "supported", None)
            keep = list(records if supported is None else supported)

            merged = {"accepted": 0, "duplicates_dropped": 0}
            published = False
            refresh_error = ""
            if keep:
                trimmed = dict(bundle, records=keep, n_records=len(keep))
                confirmed = verify_bundle(trimmed, archive=STATE.archive)
                if confirmed.accepted:
                    merged = merge_bundle(trimmed, into=RESULTS, verdict=confirmed)
                    # A durable write and publication into the live Corpus are
                    # separate outcomes. Mark before reload and retain that
                    # generation on failure; an idempotent duplicate retry then
                    # refreshes the already-present file instead of skipping it.
                    published, refresh_error = _refresh_publication(
                        STATE, wrote=bool(merged.get("accepted")),
                    )

            failed = list(getattr(verdict, "failed", []) or [])
            unsupported = list(getattr(verdict, "unsupported", []) or [])
            refused = failed + unsupported
            if refresh_error:
                note = (
                    "Verified records are stored durably, but the running "
                    "library could not refresh. Retrying this bundle is safe "
                    "and will retry publication."
                )
            elif published:
                note = (
                    "Supported prose evidence was matched to its cited page. "
                    "Locator-only table evidence remains unsupported without "
                    "localized cell proof; verified records are now live."
                )
            else:
                note = "No record met the evidence boundary; nothing was published."
            response = {
                "accepted": bool(merged.get("accepted")),
                "verified": verdict.verified,
                "merged": merged.get("accepted", 0),
                "already_here": merged.get("duplicates_dropped", 0),
                "published": published,
                "refresh_failed": bool(refresh_error),
                "refresh_error": refresh_error,
                "refused": len(refused),
                "failed": len(failed),
                "unsupported": len(unsupported),
                "why_refused": [f.get("why", "")[:160] for f in refused[:10]],
                "note": note,
            }
            self._send_json(
                response,
                status=503 if refresh_error else 200,
                headers=(
                    {"Retry-After": str(BUNDLE_BUSY_RETRY_SECONDS)}
                    if refresh_error else None
                ),
            )
        finally:
            BUNDLE_VERIFY_SLOTS.release()

    def _post_ask(self, payload: dict[str, Any]) -> None:
        assert STATE is not None
        try:
            question = _text_field(payload, "question", MAX_QUESTION_CHARS)
        except _ApiInputError as exc:
            self._send_json({"error": str(exc)}, status=exc.status)
            return
        if not question:
            self._send_json({"error": "no question"}, status=400)
            return
        if not self._rate_allowed(MODEL_RATE_LIMITER, "model"):
            return
        if not MODEL_SLOTS.acquire(blocking=False):
            self._send_json(
                {
                    "error": "model work is busy; try again later",
                    "retry_after": MODEL_BUSY_RETRY_SECONDS,
                },
                status=503,
                headers={"Retry-After": str(MODEL_BUSY_RETRY_SECONDS)},
            )
            return
        try:
            turn = STATE.jay.ask(question)
            self._send_json({
                "reply": turn.reply,
                "tools": turn.tool_calls,
                "error": turn.error,
            })
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": f"model request failed: {exc}"[:200]}, status=500)
        finally:
            MODEL_SLOTS.release()

    def _post_citation(self, payload: dict[str, Any]) -> None:
        assert STATE is not None
        try:
            ident = _text_field(payload, "identifier", MAX_IDENTIFIER_CHARS)
            quote = _text_field(
                payload, "quote", MAX_QUOTE_CHARS, strip=False,
            )
        except _ApiInputError as exc:
            self._send_json({"error": str(exc)}, status=exc.status)
            return
        raw_page = payload.get("page", 0)
        try:
            if isinstance(raw_page, bool):
                raise ValueError
            page_no = int(raw_page)
        except (TypeError, ValueError):
            page_no = 0
        if not ident or page_no < 1 or page_no > 1_000_000:
            self._send_json({"error": "need identifier and a valid page"}, status=400)
            return
        if not self._archive_identifier_allowed(ident):
            self._send_json(
                {"error": "identifier is outside the configured collection"}, status=400,
            )
            return
        if not self._rate_allowed(ARCHIVE_RATE_LIMITER, "archive"):
            return
        if not ARCHIVE_SLOTS.acquire(blocking=False):
            self._send_json(
                {
                    "error": "archive work is busy; try again later",
                    "retry_after": ARCHIVE_BUSY_RETRY_SECONDS,
                },
                status=503,
                headers={"Retry-After": str(ARCHIVE_BUSY_RETRY_SECONDS)},
            )
            return
        try:
            pages = STATE.archive.pages(ident, with_words=True)
            page = {item.page: item for item in pages}[page_no]
            citation = cite_record(
                page, {"provenance": {"source_text": quote}},
            ) if quote else cite(page, "")
            self._send_json(citation.to_dict())
        except Exception as exc:  # noqa: BLE001
            self._send_json(
                {"error": f"page not retrievable: {exc}"[:160]}, status=502,
            )
        finally:
            ARCHIVE_SLOTS.release()

    def _post_decisions(self, payload: dict[str, Any]) -> None:
        assert STATE is not None
        try:
            ident = _text_field(payload, "identifier", MAX_IDENTIFIER_CHARS)
            body = _text_field(payload, "body", MAX_DECISION_BODY_CHARS)
        except _ApiInputError as exc:
            self._send_json({"error": str(exc)}, status=exc.status)
            return
        if not ident:
            self._send_json({"error": "no identifier"}, status=400)
            return
        if not self._archive_identifier_allowed(ident):
            self._send_json(
                {"error": "identifier is outside the configured collection"}, status=400,
            )
            return
        if not self._rate_allowed(ARCHIVE_RATE_LIMITER, "archive"):
            return
        if not ARCHIVE_SLOTS.acquire(blocking=False):
            self._send_json(
                {
                    "error": "archive work is busy; try again later",
                    "retry_after": ARCHIVE_BUSY_RETRY_SECONDS,
                },
                status=503,
                headers={"Retry-After": str(ARCHIVE_BUSY_RETRY_SECONDS)},
            )
            return
        try:
            pages = STATE.archive.pages(ident)
            ledger = read_document(pages, body=body)
            self._send_json(ledger.report())
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)[:160]}, status=502)
        finally:
            ARCHIVE_SLOTS.release()

    def _post_evidence_view(self, view: str, work: Any) -> None:
        """Run one cached archive/ECCC view without queueing duplicate builds."""
        if not self._rate_allowed(ARCHIVE_RATE_LIMITER, "evidence"):
            return
        assert STATE is not None
        # Lightweight test/fake State objects retain the original guarded path.
        if not hasattr(STATE, "evidence_build_lock"):
            if not ARCHIVE_SLOTS.acquire(blocking=False):
                self._send_json(
                    {
                        "error": "evidence work is busy; try again later",
                        "retry_after": ARCHIVE_BUSY_RETRY_SECONDS,
                    },
                    status=503,
                    headers={"Retry-After": str(ARCHIVE_BUSY_RETRY_SECONDS)},
                )
                return
            try:
                self._send_json(work())
            except Exception as exc:  # noqa: BLE001
                self._send_json(
                    {"error": f"evidence request failed: {exc}"[:200]}, status=502,
                )
            finally:
                ARCHIVE_SLOTS.release()
            return

        # Acquire the view gate before deciding warm/cold. Mutation invalidates
        # these caches under the same gate, so it cannot clear a warm cache
        # between our check and read and accidentally bypass ARCHIVE_SLOTS.
        build_lock = STATE.evidence_build_lock(view)
        owns_build = build_lock.acquire(blocking=False)
        if not owns_build:
            self._send_json(
                {
                    "error": f"{view} is being built; try again shortly",
                    "retry_after": ARCHIVE_BUSY_RETRY_SECONDS,
                },
                status=503,
                headers={"Retry-After": str(ARCHIVE_BUSY_RETRY_SECONDS)},
            )
            return
        cold = not STATE.evidence_cached(view)
        owns_archive_slot = False
        if cold:
            owns_archive_slot = ARCHIVE_SLOTS.acquire(blocking=False)
        if cold and not owns_archive_slot:
            build_lock.release()
            self._send_json(
                {
                    "error": "evidence work is busy; try again later",
                    "retry_after": ARCHIVE_BUSY_RETRY_SECONDS,
                },
                status=503,
                headers={"Retry-After": str(ARCHIVE_BUSY_RETRY_SECONDS)},
            )
            return
        try:
            payload = STATE.build_evidence_view(view)
            self._send_json(payload)
        except Exception as exc:  # noqa: BLE001
            self._send_json(
                {"error": f"evidence request failed: {exc}"[:200]}, status=502,
            )
        finally:
            if owns_archive_slot:
                ARCHIVE_SLOTS.release()
            build_lock.release()

    def _post_frontier(self, payload: dict[str, Any]) -> None:
        assert STATE is not None
        self._post_evidence_view("frontier", STATE.frontier)

    def _post_ledger(self, payload: dict[str, Any]) -> None:
        assert STATE is not None
        self._post_evidence_view("ledger", STATE.ledger)

    def _post_watershed(self, payload: dict[str, Any]) -> None:
        assert STATE is not None
        self._post_evidence_view("watershed", STATE.watershed)

    def _post_flag(self, payload: dict[str, Any]) -> None:
        assert STATE is not None
        try:
            claim_id = _text_field(payload, "claim", MAX_FLAG_CLAIM_CHARS)
            reason = _text_field(
                payload, "reason", MAX_FLAG_REASON_CHARS, strip=False,
            )
        except _ApiInputError as exc:
            self._send_json({"error": str(exc)}, status=exc.status)
            return
        if not claim_id:
            self._send_json({"error": "no claim"}, status=400)
            return
        if not self._rate_allowed(MUTATION_RATE_LIMITER, "mutation"):
            return
        if not STATE.has_claim(claim_id):
            self._send_json(
                {"error": "claim does not exist; no flag was recorded"}, status=404,
            )
            return
        with FLAGS_LOCK:
            flag_key = (self._direct_peer(), claim_id)
            duplicate = flag_key in FLAG_KEYS
            if not duplicate:
                FLAG_KEYS.add(flag_key)
                FLAGS.append(Flag(claim_id=claim_id, reason=reason))
            n_flags = len(FLAGS)
        self._send_json({
            "ok": True,
            "recorded": not duplicate,
            "flags": n_flags,
            "note": (
                ("Already counted for this claim from this peer. " if duplicate
                 else "Recorded. ")
                + "A flag is counted and shown; it does not change the record. "
                "To change what is shown, cite a page and quote a sentence -- "
                "then the archive evidence can be checked."
            ),
        })

    def _post_submit(self, payload: dict[str, Any]) -> None:
        assert STATE is not None
        try:
            identifier = _text_field(payload, "identifier", MAX_IDENTIFIER_CHARS)
            quote = _text_field(
                payload, "quote", MAX_QUOTE_CHARS, strip=False,
            )
            parameter = _text_field(
                payload, "parameter", MAX_SUBMIT_TEXT_CHARS,
            )
            unit = _text_field(payload, "unit", MAX_SUBMIT_TEXT_CHARS)
            place = _text_field(payload, "place", MAX_SUBMIT_TEXT_CHARS)
            facility = _text_field(payload, "facility", MAX_SUBMIT_TEXT_CHARS)
            period = _text_field(payload, "period", MAX_SUBMIT_TEXT_CHARS)
            stream = _text_field(payload, "stream", MAX_SUBMIT_TEXT_CHARS) or "unknown"
            who = _text_field(payload, "who", 60) or "anonymous"
            note = _text_field(
                payload, "note", MAX_SUBMIT_TEXT_CHARS, strip=False,
            )
            disputes = _text_field(
                payload, "disputes", MAX_FLAG_CLAIM_CHARS,
            )
        except _ApiInputError as exc:
            self._send_json({"error": str(exc)}, status=exc.status)
            return

        raw_page = payload.get("page", 0)
        try:
            if isinstance(raw_page, bool):
                raise ValueError
            page_no = int(raw_page)
        except (TypeError, ValueError):
            page_no = 0
        if not identifier or not quote or page_no < 1 or page_no > 1_000_000:
            self._send_json(
                {"error": "identifier, positive page, and quote are required"},
                status=400,
            )
            return
        if not self._archive_identifier_allowed(identifier):
            self._send_json(
                {"error": "identifier is outside the configured collection"}, status=400,
            )
            return

        raw_value = payload.get("value")
        if isinstance(raw_value, str):
            if len(raw_value) > 100:
                self._send_json(
                    {"error": "value exceeds the 100-character limit"}, status=413,
                )
                return
            try:
                value: Any = float(raw_value)
            except ValueError:
                self._send_json({"error": "value must be a finite number"}, status=400)
                return
            if not math.isfinite(value):
                self._send_json({"error": "value must be finite"}, status=400)
                return
        elif raw_value is None:
            self._send_json({"error": "value is required"}, status=400)
            return
        elif isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            self._send_json({"error": "value must be text or a number"}, status=400)
            return
        elif not math.isfinite(float(raw_value)):
            self._send_json({"error": "value must be finite"}, status=400)
            return
        else:
            value = raw_value

        if not parameter:
            self._send_json({"error": "parameter is required"}, status=400)
            return

        submitted_record = {
            "parameter": parameter,
            "value": value,
            "unit": unit or None,
            "place": place or None,
            "facility": facility or None,
            "period": period or None,
            "stream": stream,
            "kind": "observation",
            "provenance": {
                "identifier": identifier,
                "page": page_no,
                "source_text": quote,
            },
        }
        schema_problems = record_problems(submitted_record)
        if schema_problems:
            self._send_json(
                {"error": "invalid record: " + "; ".join(schema_problems)},
                status=400,
            )
            return

        if not self._rate_allowed(MUTATION_RATE_LIMITER, "mutation"):
            return
        if not self._rate_allowed(ARCHIVE_RATE_LIMITER, "archive"):
            return
        if not ARCHIVE_SLOTS.acquire(blocking=False):
            self._send_json(
                {
                    "error": "archive work is busy; try again later",
                    "retry_after": ARCHIVE_BUSY_RETRY_SECONDS,
                },
                status=503,
                headers={"Retry-After": str(ARCHIVE_BUSY_RETRY_SECONDS)},
            )
            return
        try:
            try:
                outcome = submit_claim(
                    submitted_record,
                    contributor=who,
                    note=note,
                    disputes=disputes,
                    archive=STATE.archive,
                    directory=CONTRIBUTIONS,
                )
            except Exception as exc:  # noqa: BLE001
                self._send_json(
                    {"error": f"submission failed: {exc}"[:200]}, status=502,
                )
                return

            response = outcome.to_dict()
            published = False
            refresh_error = ""
            if outcome.standing.verified:
                # Accepted individual contributions live outside RESULTS for
                # provenance, but publication joins them into the public Corpus
                # and creates a Jay instance bound to that new corpus. A
                # verified replay also services an earlier pending generation
                # after reload failed.
                published, refresh_error = _refresh_publication(
                    STATE, wrote=outcome.stored,
                )
            response.update({
                "published": published,
                "refresh_failed": bool(refresh_error),
                "refresh_error": refresh_error,
            })
            if refresh_error:
                response["what_happens_now"] = (
                    "The verified reading is stored durably, but the running "
                    "library could not refresh. Retrying this submission is "
                    "safe and will retry publication."
                )
            self._send_json(
                response,
                status=503 if refresh_error else 200,
                headers=(
                    {"Retry-After": str(ARCHIVE_BUSY_RETRY_SECONDS)}
                    if refresh_error else None
                ),
            )
        finally:
            ARCHIVE_SLOTS.release()

    def do_GET(self) -> None:  # noqa: N802
        assert STATE is not None
        url = urlparse(self.path)
        q = parse_qs(url.query)

        if url.path in ("/", "/index.html"):
            self._send(STATE.html().encode(), "text/html; charset=utf-8")
            return

        if url.path.startswith("/static/"):
            name = url.path.split("/static/", 1)[1]
            # The public asset set is intentionally tiny. Reject everything
            # else lexically before constructing or resolving an attacker-
            # selected path; on Windows, resolving a drive or UNC path can
            # itself touch an out-of-tree filesystem. The containment check
            # remains as a second boundary against an in-tree symlink.
            if name not in PUBLIC_STATIC_ASSETS:
                self.send_error(404)
                return
            static_dir = (Path(__file__).parent / "static").resolve()
            try:
                f = (static_dir / name).resolve()
            except (OSError, ValueError):
                self.send_error(404)
                return
            # Containment must be established before *any* filesystem probe.
            # is_file() on an escaped drive/UNC/symlink target leaks existence
            # even when the request is ultimately rejected.
            if not f.is_relative_to(static_dir) or not f.is_file():
                self.send_error(404)
                return
            ctype = ("text/css" if name.endswith(".css")
                     else "application/javascript" if name.endswith(".js")
                     else "application/octet-stream")
            self._send(f.read_bytes(), ctype + "; charset=utf-8")
            return

        if url.path in POST_ONLY_ENDPOINTS:
            self._method_not_allowed("POST")
            return

        if url.path == "/api/library.json":
            # The whole dataset, as a bundle anyone can take and re-verify.
            # A shared instance that could only be written to and not read from
            # would be a silo: the point of publishing this is that somebody who
            # mistrusts the instance can pull everything, check it against
            # archive.org themselves, and run their own.
            records = [r.to_dict() for r in STATE.corpus.records]
            self._send(json.dumps({
                "bundle_version": 1,
                "contributor": "shared instance",
                "note": "the whole library; re-verify it before believing it",
                "bundle_id": bundle_id(records),
                "n_records": len(records),
                "identifiers": sorted({
                    (r.get("provenance") or {}).get("identifier", "")
                    for r in records} - {""}),
                "records": records,
            }).encode(), "application/json")
            return

        if url.path == "/api/accuracy":
            self._send(json.dumps(STATE.gold).encode(), "application/json")
            return

        if url.path == "/api/places.geojson":
            self._send(json.dumps(STATE.geojson()).encode(), "application/json")
            return

        if url.path == "/api/town":
            out = STATE.town((q.get("place") or [""])[0], (q.get("raw") or [""])[0])
            self._send(json.dumps(out).encode(), "application/json")
            return

        if url.path == "/api/quiet":
            self._send(json.dumps(what_went_quiet()).encode(), "application/json")
            return

        if url.path == "/api/story":
            place = (q.get("place") or [""])[0]
            self._send(
                json.dumps(read_me_the_record(STATE.corpus, place)).encode(),
                "application/json",
            )
            return

        if url.path == "/api/judge":
            try:
                out = judge_reading(
                    STATE.corpus,
                    (q.get("parameter") or ["BOD"])[0],
                    float((q.get("value") or ["0"])[0]),
                    (q.get("unit") or ["mg/L"])[0],
                    int((q.get("year") or ["1969"])[0]),
                )
            except ValueError as exc:
                out = {"error": str(exc)}
            self._send(json.dumps(out).encode(), "application/json")
            return

        self.send_error(404)

    def log_message(self, *args: Any) -> None:  # keep the console readable
        pass


def main(port: int = 8765, open_browser: bool = True) -> int:
    global STATE
    STATE = State()
    print(f"Concordance — {len(STATE.places)} municipalities located, "
          f"{len(STATE.corpus.records)} source-linked records loaded")
    url = f"http://localhost:{port}/"
    print(f"serving {url}   (ctrl-c to stop)")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    try:
        ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
