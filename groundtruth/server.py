"""A running instance you can click.

    python -m groundtruth.server

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
import re
import webbrowser
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .archive import Archive
from .citations import cite, cite_record
from .contribute import bundle_id, merge_bundle, verify_bundle
from .decisions import read_document
from .frontier import load as load_frontier
from .disputes import (
    Flag, load_claims, load_contributions, load_vision_records,
    resolve as resolve_claims, submit as submit_claim,
)
from .parameters import resolve as resolve_parameter
from .honu import Honu
from .library import ask
from .portal import render
from .science import series_from_records
from .tools import Corpus, find_my_town, judge_reading, read_me_the_record, what_went_quiet

RESULTS = Path("data/results")

#: Flags people have raised, in memory. Deliberately not persisted yet: a flag
#: changes nothing about the data by design, so losing them on restart costs a
#: tally and no evidence. Persisting them is a storage decision, not a trust
#: one, and it can wait until there is somewhere to put them.
FLAGS: list[Flag] = []

#: Largest bundle accepted over HTTP. A shared instance takes uploads from
#: anyone, so the size limit is the one place it does need a rule -- and
#: 8 MB is roughly forty thousand readings, far more than one town.
MAX_BUNDLE_BYTES = 8 * 1024 * 1024

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


class State:
    """Everything the server can answer from, loaded once at startup."""

    def __init__(self) -> None:
        self.corpus = Corpus.load_dir(RESULTS)
        self.silence = self._read("silence_report.json")
        self.census = self._read("corpus_census.json")
        self.gold = self._read("gold_report.json")
        self.places = self._geocode()
        self.archive = Archive()
        # Resolving the ledger fetches every cited page, so it is built on
        # first request and held until a flag or a new reading changes it.
        self._ledger: dict[str, Any] | None = None
        # Lazily built: constructing it is cheap, but every request that
        # uses it needs a model, which may not be present.
        self.honu = Honu(self.corpus)

    def invalidate_ledger(self) -> None:
        self._ledger = None
        self._frontier = None

    def frontier(self) -> dict[str, Any]:
        """Questions the archive is one document away from answering.

        Cached alongside the ledger: it reads every extraction on disk and the
        silence report, and the answer only changes when something is read.
        """
        if getattr(self, "_frontier", None) is not None:
            return self._frontier  # type: ignore[return-value]

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

        self._frontier = {
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
        return self._frontier

    def ledger(self) -> dict[str, Any]:
        """Every claim's standing, with the contested ones carrying their crops.

        The crops are the point. "These two readings disagree" is useless on its
        own; with a picture of each sentence a reader settles it themselves,
        which is what lets this run without a moderator.
        """
        if self._ledger is not None:
            return self._ledger

        # The machine's readings and people's submissions go in together, on
        # the same footing. Nothing downstream can tell which is which,
        # because nothing downstream is allowed to care.
        claims = (load_claims(RESULTS) + load_vision_records()
                  + load_contributions())
        resolved = resolve_claims(claims, FLAGS, archive=self.archive)
        report = resolved.report()

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
                "n_flags": len(slot.flags),
                "readings": entries,
            })

        report["contested_detail"] = contested
        self._ledger = report
        return report

    @staticmethod
    def _read(name: str) -> dict[str, Any]:
        p = RESULTS / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def _geocode(self) -> list[dict[str, Any]]:
        try:
            from .places import resolve
        except Exception:  # noqa: BLE001
            return []
        have = {(r.place or "").lower() for r in self.corpus.records}
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

    def reload(self) -> None:
        """Re-read the library after something has been added to it."""
        self.corpus = Corpus.load_dir(RESULTS)
        self.places = self._geocode()

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
        if getattr(self, "_watershed", None) is not None:
            return self._watershed  # type: ignore[return-value]

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

        self._watershed = out
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

    #: Charted in this order. Removal percentages first because they are the
    #: number a non-specialist can actually read: how much the plant took out.
    SERIES = [
        ("BOD removal", None, "BOD removal"),
        ("suspended solids removal", None, "Suspended solids removal"),
        ("BOD", "effluent", "BOD discharged"),
        ("suspended solids", "effluent", "Solids discharged"),
        ("BOD", "influent", "BOD arriving"),
        ("daily flow", None, "Daily flow"),
        ("total flow", None, "Total annual flow"),
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
        # One facility at a time. Effluent and tap water are opposite
        # measurements and must never share a panel.
        facilities = Counter(r.facility or "unclassified" for r in mine)
        if len(facilities) > 1:
            main = facilities.most_common(1)[0][0]
            mine = [r for r in mine if (r.facility or "unclassified") == main]
            out["facility"] = main

        series = []
        for param, stream, label in self.SERIES:
            s = series_from_records(mine, parameter=param, stream=stream)
            if not s.points:
                continue
            rows = []
            want_param = resolve_parameter(param)
            for y, v, _c in s.points:
                # Match the ORIGINAL record by year, parameter and value -- not
                # by year alone. Matching on year attached the flow sentence to
                # every reading in the panel, so each number displayed a quotation
                # that had nothing to do with it. The provenance was not merely
                # imprecise, it was wrong, which is worse than showing none: the
                # entire trust model here is "this sentence is where this number
                # came from".
                src = None
                for r in mine:
                    if not (r.period and str(r.period)[:4] == str(int(y))):
                        continue
                    got = resolve_parameter(r.parameter, r.unit)
                    if want_param is not None and (got is None or got.key != want_param.key):
                        continue
                    if stream is not None and r.stream != stream:
                        continue
                    src = r
                    break
                rows.append({
                    "period": int(y),
                    "parameter": label,
                    "value": f"{v:.4g}",
                    "unit": s.unit,
                    "read_from": (src.provenance.source_text[:150] if src and src.provenance else ""),
                    "page_url": (src.provenance.page_url if src and src.provenance else ""),
                    # Enough for the portal to ask /api/citation for a picture of
                    # this exact sentence. The quote is sent whole rather than
                    # truncated, because the crop is found by matching its words
                    # against the page's OCR and 150 characters is not always a
                    # sentence.
                    "identifier": (src.provenance.identifier if src and src.provenance else ""),
                    "page": (src.provenance.page if src and src.provenance else 0),
                    "quote": (src.provenance.source_text if src and src.provenance else ""),
                })
            series.append({
                "label": label, "unit": s.unit,
                "points": [[int(y), v] for y, v, _ in s.points],
                "rows": rows,
            })
        out["series"] = series
        return out


STATE: State | None = None


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, ctype: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- receiving readings from other machines ---------------------------

    def do_POST(self) -> None:  # noqa: N802
        """Accept a bundle of readings from somebody else's machine.

        This is the destination the distributed model was missing. Until it
        existed, `library.ask` read a town on your laptop and `share.py export`
        packaged it, and there the trail went cold -- "your machine reads it for
        everyone" had nowhere to send the result.

        Nothing about the sender is examined and no account is required, because
        nothing about the sender is relevant. Every record is re-verified here,
        against archive.org, on the same terms this instance judges its own
        output: is that sentence on that page, and is that value in it. A bundle
        from a stranger and one from the maintainer are handled identically.

        The instance is a convenience, not an authority. It holds no key that
        anyone else lacks, and anyone who mistrusts it can pull the dataset,
        re-verify every record themselves, and run their own -- which is the
        property that stops a shared server becoming a single point of trust.
        """
        assert STATE is not None
        url = urlparse(self.path)
        if url.path != "/api/bundle":
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BUNDLE_BYTES:
            self._send(json.dumps({
                "accepted": False,
                "why": f"bundle must be between 1 byte and {MAX_BUNDLE_BYTES} bytes",
            }).encode(), "application/json")
            return

        try:
            bundle = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            self._send(json.dumps({
                "accepted": False, "why": f"not readable as JSON: {str(exc)[:120]}",
            }).encode(), "application/json")
            return

        records = bundle.get("records") if isinstance(bundle, dict) else None
        if not isinstance(records, list) or not records:
            self._send(json.dumps({
                "accepted": False,
                "why": "no records in the bundle",
            }).encode(), "application/json")
            return

        verdict = verify_bundle(bundle, archive=STATE.archive)

        # Keep what the archive supports and report the rest, rather than
        # refusing the whole bundle over one unverifiable reading. Every
        # record's standing is individually known and the ledger has a state
        # for "unsupported", so what is left out is a reported absence.
        failed_keys = {
            (f.get("identifier"), f.get("page"), (f.get("quote") or "")[:120],
             repr(f.get("value"))) for f in verdict.failed
        }
        keep = []
        for record in records:
            prov = record.get("provenance") or {}
            key = (prov.get("identifier"), prov.get("page"),
                   (prov.get("source_text") or "")[:120], repr(record.get("value")))
            if key not in failed_keys:
                keep.append(record)

        merged = {"accepted": 0, "duplicates_dropped": 0}
        if keep:
            trimmed = dict(bundle, records=keep, n_records=len(keep))
            confirmed = verify_bundle(trimmed, archive=STATE.archive)
            if confirmed.accepted:
                merged = merge_bundle(trimmed, into=RESULTS, verdict=confirmed)
                STATE.reload()
                STATE.invalidate_ledger()

        self._send(json.dumps({
            "accepted": bool(merged.get("accepted")),
            "verified": verdict.verified,
            "merged": merged.get("accepted", 0),
            "already_here": merged.get("duplicates_dropped", 0),
            "refused": len(verdict.failed),
            "why_refused": [f.get("why", "")[:160] for f in verdict.failed[:10]],
            "note": (
                "Every record was re-checked against the pages it cites. What "
                "verified is now in the library on the same footing as "
                "everything else, and nothing was taken on trust."
            ),
        }).encode(), "application/json")

    def do_GET(self) -> None:  # noqa: N802
        assert STATE is not None
        url = urlparse(self.path)
        q = parse_qs(url.query)

        if url.path in ("/", "/index.html"):
            self._send(STATE.html().encode(), "text/html; charset=utf-8")
            return

        if url.path.startswith("/static/"):
            name = url.path.split("/static/", 1)[1]
            f = Path(__file__).parent / "static" / name
            if not f.is_file() or ".." in name:
                self.send_error(404)
                return
            ctype = ("text/css" if name.endswith(".css")
                     else "application/javascript" if name.endswith(".js")
                     else "application/octet-stream")
            self._send(f.read_bytes(), ctype + "; charset=utf-8")
            return

        if url.path == "/api/ask":
            question = (q.get("q") or [""])[0].strip()
            if not question:
                self._send(json.dumps({"error": "no question"}).encode(), "application/json")
                return
            turn = STATE.honu.ask(question)
            self._send(json.dumps({
                "reply": turn.reply,
                "tools": turn.tool_calls,
                "error": turn.error,
            }).encode(), "application/json")
            return

        if url.path == "/api/read":
            # Somebody asked for a town nobody has read. Their machine reads it,
            # and it is in the library for everyone from then on. Contributing is
            # not a separate act here -- it is what getting the data consists of.
            place = (q.get("place") or [""])[0].strip()
            if not place:
                self._send(json.dumps({"error": "no place"}).encode(), "application/json")
                return
            answer = ask(place, read_if_missing=True)
            STATE.reload()
            self._send(json.dumps({
                "place": place, "source": answer.source,
                "records": len(answer.records), "documents": answer.documents,
                "seconds": round(answer.seconds), "verified": answer.verified,
                "contributed": answer.contributed,
                "unknown_parameters": answer.unknown_parameters[:20],
                "message": answer.describe(),
            }).encode(), "application/json")
            return

        if url.path == "/api/citation":
            # The picture of the paper. Every number on every chart can produce
            # one, which is the difference between provenance that exists and
            # provenance anybody uses.
            ident = (q.get("identifier") or [""])[0]
            quote = (q.get("quote") or [""])[0]
            try:
                page_no = int((q.get("page") or ["0"])[0])
            except ValueError:
                page_no = 0
            if not ident or page_no < 1:
                self._send(json.dumps({"error": "need identifier and page"}).encode(),
                           "application/json")
                return
            try:
                page = {p.page: p for p in STATE.archive.pages(ident, with_words=True)}[page_no]
            except Exception as exc:  # noqa: BLE001
                self._send(json.dumps({"error": f"page not retrievable: {exc}"[:160]}).encode(),
                           "application/json")
                return
            citation = cite_record(page, {"provenance": {"source_text": quote}}) \
                if quote else cite(page, "")
            self._send(json.dumps(citation.to_dict()).encode(), "application/json")
            return

        if url.path == "/api/frontier":
            # What reading one more document would make answerable, and for
            # whom. The only ordering of eleven million pages that serves
            # somebody rather than the person who chose the subject.
            self._send(json.dumps(STATE.frontier()).encode(), "application/json")
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

        if url.path == "/api/ledger":
            # Settled, contested and unsupported -- the state of every claim,
            # with nobody having adjudicated any of it.
            self._send(json.dumps(STATE.ledger()).encode(), "application/json")
            return

        if url.path == "/api/flag":
            # An objection with no evidence. It is counted and shown and it
            # changes nothing, which is what makes it safe to accept from
            # anyone without moderating it.
            claim_id = (q.get("claim") or [""])[0].strip()
            if not claim_id:
                self._send(json.dumps({"error": "no claim"}).encode(), "application/json")
                return
            FLAGS.append(Flag(claim_id=claim_id,
                              reason=(q.get("reason") or [""])[0][:400]))
            STATE.invalidate_ledger()
            self._send(json.dumps({
                "ok": True, "flags": len(FLAGS),
                "note": "Recorded. A flag is counted and shown; it does not change "
                        "the record. To change what is shown, cite a page and quote "
                        "a sentence -- then the archive decides, not us.",
            }).encode(), "application/json")
            return

        if url.path == "/api/submit":
            # A reading offered by a person. Checked by the same code that
            # judges the machine's own output, and by nothing else -- there is
            # no queue for it to sit in and nobody to approve it.
            provenance = {
                "identifier": (q.get("identifier") or [""])[0].strip(),
                "source_text": (q.get("quote") or [""])[0],
            }
            try:
                provenance["page"] = int((q.get("page") or ["0"])[0])
            except ValueError:
                provenance["page"] = 0
            raw_value = (q.get("value") or [""])[0]
            try:
                value: Any = float(raw_value)
            except ValueError:
                value = raw_value or None

            outcome = submit_claim(
                {
                    "parameter": (q.get("parameter") or [""])[0].strip(),
                    "value": value,
                    "unit": (q.get("unit") or [""])[0].strip() or None,
                    "place": (q.get("place") or [""])[0].strip() or None,
                    "facility": (q.get("facility") or [""])[0].strip() or None,
                    "period": (q.get("period") or [""])[0].strip() or None,
                    "stream": (q.get("stream") or ["unknown"])[0].strip(),
                    "kind": "observation",
                    "provenance": provenance,
                },
                contributor=(q.get("who") or ["anonymous"])[0][:60],
                note=(q.get("note") or [""])[0][:400],
                disputes=(q.get("disputes") or [""])[0].strip(),
                archive=STATE.archive,
            )
            STATE.invalidate_ledger()
            self._send(json.dumps(outcome.to_dict()).encode(), "application/json")
            return

        if url.path == "/api/decisions":
            ident = (q.get("identifier") or [""])[0].strip()
            if not ident:
                self._send(json.dumps({"error": "no identifier"}).encode(),
                           "application/json")
                return
            try:
                pages = STATE.archive.pages(ident)
            except Exception as exc:  # noqa: BLE001
                self._send(json.dumps({"error": str(exc)[:160]}).encode(),
                           "application/json")
                return
            ledger = read_document(pages, body=(q.get("body") or [""])[0])
            self._send(json.dumps(ledger.report()).encode(), "application/json")
            return

        if url.path == "/api/watershed":
            self._send(json.dumps(STATE.watershed()).encode(), "application/json")
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
    print(f"Ground Truth — {len(STATE.places)} municipalities located, "
          f"{len(STATE.corpus.records)} measurements loaded")
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
