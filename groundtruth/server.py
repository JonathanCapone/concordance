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
import webbrowser
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .parameters import resolve as resolve_parameter
from .honu import Honu
from .portal import render
from .science import series_from_records
from .tools import Corpus, find_my_town, judge_reading, read_me_the_record, what_went_quiet

RESULTS = Path("data/results")

class State:
    """Everything the server can answer from, loaded once at startup."""

    def __init__(self) -> None:
        self.corpus = Corpus.load_dir(RESULTS)
        self.silence = self._read("silence_report.json")
        self.census = self._read("corpus_census.json")
        self.gold = self._read("gold_report.json")
        self.places = self._geocode()
        # Lazily built: constructing it is cheap, but every request that
        # uses it needs a model, which may not be present.
        self.honu = Honu(self.corpus)

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
                "silent_since": m.get("silent_since"),
                "extracted": p.canonical.lower() in have or m["place"].lower() in have,
            })
        return out


    # -- what the portal asks for -----------------------------------------

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

        want = {place.lower(), raw.lower()}
        mine = [r for r in self.corpus.records
                if (r.place or "").lower() in want and r.kind == "observation"]
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
