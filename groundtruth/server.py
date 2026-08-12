"""A running instance you can click.

    python -m groundtruth.server

Standard library only, like the rest of the core -- `http.server` rather than a
framework, and a hand-projected SVG map rather than a tile library, so the whole
thing starts with no install, no API key, and no network. That last part is not
tidiness: it means the demo works on conference wifi, and it means a reviewer can
run it before deciding whether to trust anything it says.

Everything it serves comes from files already produced by the pipeline. The
server computes nothing it cannot show you the source of.
"""

from __future__ import annotations

import json
import math
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .tools import Corpus, find_my_town, judge_reading, read_me_the_record, what_went_quiet

RESULTS = Path("data/results")

# Ontario, roughly. Used for a simple equirectangular projection with a cosine
# correction at the mid-latitude -- adequate for a province-scale locator map and
# far less trouble than a projection library we would then have to depend on.
LAT0, LAT1 = 41.5, 57.0
LON0, LON1 = -95.5, -74.0
MID = math.cos(math.radians((LAT0 + LAT1) / 2))


def project(lat: float, lon: float, w: int, h: int) -> tuple[float, float]:
    x = (lon - LON0) / (LON1 - LON0) * w
    y = (1 - (lat - LAT0) / (LAT1 - LAT0)) * h
    # Squeeze x so the province is not stretched sideways at this latitude.
    cx = w / 2
    return cx + (x - cx) * MID / 0.62, y


class State:
    """Everything the server can answer from, loaded once at startup."""

    def __init__(self) -> None:
        self.corpus = Corpus.load_dir(RESULTS)
        self.silence = self._read("silence_report.json")
        self.census = self._read("corpus_census.json")
        self.gold = self._read("gold_report.json")
        self.places = self._geocode()

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


STATE: State | None = None


def page() -> str:
    assert STATE is not None
    W, H = 900, 620
    dots = []
    for p in STATE.places:
        x, y = project(p["lat"], p["lon"], W, H)
        r = 3 + min(4.0, p["years"] * 0.45)
        cls = "has" if p["extracted"] else "dot"
        dots.append(
            f'<circle class="{cls}" cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" '
            f'data-place="{p["place"]}" data-raw="{p["raw"]}" '
            f'data-first="{p["first"]}" data-last="{p["last"]}" '
            f'data-years="{p["years"]}" data-silent="{p.get("silent_since") or ""}">'
            f'<title>{p["place"]} — {p["years"]} reports, {p["first"]}–{p["last"]}</title></circle>'
        )

    n_ext = sum(1 for p in STATE.places if p["extracted"])
    totals = STATE.gold.get("totals", {})
    stop = STATE.silence.get("largest_simultaneous_stop", {})

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ground Truth — live</title><style>
:root{{--bg:#fbfaf8;--panel:#fff;--ink:#17150f;--muted:#6b6559;--line:#e2ded5;--hit:#b5651d}}
@media(prefers-color-scheme:dark){{:root{{--bg:#14130f;--panel:#1c1a16;--ink:#f2efe8;
 --muted:#9b948a;--line:#2e2b25;--hit:#d99a5b}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
 font:15px/1.6 ui-sans-serif,system-ui,-apple-system,sans-serif}}
header{{padding:20px 26px 12px}}
h1{{font-size:22px;font-weight:500;margin:0 0 2px;letter-spacing:-.02em}}
.sub{{color:var(--muted);font-size:13px}}
.wrap{{display:grid;grid-template-columns:1fr 380px;gap:18px;padding:8px 26px 40px;
 align-items:start}}
@media(max-width:900px){{.wrap{{grid-template-columns:1fr}}}}
.panel{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px}}
svg.map{{width:100%;height:auto;display:block}}
.dot{{fill:var(--muted);opacity:.5;cursor:pointer}}
.dot:hover{{opacity:.9}}
.has{{fill:var(--hit);opacity:.85;cursor:pointer}}
.has:hover{{opacity:1}}
.sel{{stroke:var(--ink);stroke-width:2}}
.stats{{display:flex;gap:22px;flex-wrap:wrap;margin:0 0 12px}}
.stat .v{{font-size:19px;font-weight:500;font-variant-numeric:tabular-nums}}
.stat .l{{font-size:11px;color:var(--muted)}}
h2{{font-size:15px;font-weight:500;margin:0 0 8px}}
.muted{{color:var(--muted);font-size:13px}}
table{{border-collapse:collapse;width:100%;font-size:12.5px;margin-top:8px}}
td,th{{text-align:left;padding:5px 6px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{color:var(--muted);font-weight:500}}
td.n{{text-align:right;font-family:ui-monospace,monospace;white-space:nowrap}}
a{{color:inherit}}
.q{{color:var(--muted);font-style:italic}}
.legend{{font-size:12px;color:var(--muted);margin-top:6px}}
.sw{{display:inline-block;width:9px;height:9px;border-radius:50%;vertical-align:middle}}
</style></head><body>
<header>
  <h1>Ground Truth</h1>
  <div class="sub">Measurements read out of {STATE.census.get('extrapolation',{}).get('corpus_items',104241):,}
  scanned Canadian government documents. Click a town.</div>
</header>
<div class="wrap">
  <div class="panel">
    <div class="stats">
      <div class="stat"><div class="v">{len(STATE.places)}</div><div class="l">municipalities located</div></div>
      <div class="stat"><div class="v">{n_ext}</div><div class="l">read so far</div></div>
      <div class="stat"><div class="v">{len(STATE.corpus.records)}</div><div class="l">measurements recovered</div></div>
      <div class="stat"><div class="v">{totals.get('precision',0):.0%}</div><div class="l">extraction precision</div></div>
      <div class="stat"><div class="v">{stop.get('municipalities','—')}</div><div class="l">went silent in {stop.get('year','—')}</div></div>
    </div>
    <svg class="map" viewBox="0 0 {W} {H}" role="img"
         aria-label="Map of Ontario municipalities that filed water pollution control plant reports">
      {''.join(dots)}
    </svg>
    <div class="legend">
      <span class="sw" style="background:var(--hit)"></span> read &nbsp;
      <span class="sw" style="background:var(--muted);opacity:.5"></span> located, not yet read &nbsp;·&nbsp;
      dot size = number of surviving reports
    </div>
  </div>
  <div class="panel" id="side">
    <h2>Pick a town</h2>
    <p class="muted">Orange dots have been read. Every number that comes back links to the
    scanned page it was read from.</p>
  </div>
</div>
<script>
const side = document.getElementById('side');
let current = null;
document.querySelectorAll('circle').forEach(c => c.addEventListener('click', async () => {{
  if (current) current.classList.remove('sel');
  c.classList.add('sel'); current = c;
  const place = c.dataset.place, raw = c.dataset.raw;
  side.innerHTML = '<h2>' + place + '</h2><p class="muted">loading…</p>';
  const r = await fetch('/api/town?place=' + encodeURIComponent(place)
                        + '&raw=' + encodeURIComponent(raw));
  const d = await r.json();
  let h = '<h2>' + place + '</h2>';
  h += '<p class="muted">' + c.dataset.years + ' surviving reports, '
     + c.dataset.first + '–' + c.dataset.last
     + (c.dataset.silent ? ' · silent since ' + c.dataset.silent : '') + '</p>';
  if (!d.found) {{
    h += '<p class="muted">Not read yet. The pipeline works town by town; this one is '
       + 'located but its reports have not been extracted.</p>';
  }} else {{
    h += '<p class="muted">' + d.n_measurements + ' measurements from '
       + d.sources.length + ' documents.</p><table><tr><th>year</th><th>what</th>'
       + '<th class="n">value</th><th>check</th></tr>';
    d.readings.forEach(x => {{
      h += '<tr><td class="n">' + (x.period||'') + '</td><td>' + x.parameter
        + '</td><td class="n">' + (x.value ?? '') + ' ' + (x.unit||'')
        + '</td><td><a href="' + x.page_url + '" target="_blank" rel="noopener">scan</a></td></tr>'
        + '<tr><td></td><td colspan="3" class="q">&ldquo;' + (x.read_from||'') + '&rdquo;</td></tr>';
    }});
    h += '</table>';
  }}
  side.innerHTML = h;
}}));
</script></body></html>"""


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
            self._send(page().encode(), "text/html; charset=utf-8")
            return

        if url.path == "/api/town":
            place = (q.get("place") or [""])[0]
            raw = (q.get("raw") or [""])[0]
            out = find_my_town(STATE.corpus, place)
            if not out.get("found") and raw:
                out = find_my_town(STATE.corpus, raw)
            if out.get("found"):
                want = {place.lower(), raw.lower()}
                rows = [
                    {
                        "period": r.period, "parameter": r.parameter, "value": r.value,
                        "unit": r.unit, "kind": r.kind,
                        "read_from": (r.provenance.source_text[:160] if r.provenance else ""),
                        "page_url": (r.provenance.page_url if r.provenance else ""),
                    }
                    for r in STATE.corpus.records
                    if (r.place or "").lower() in want and r.kind == "observation"
                ]
                rows.sort(key=lambda x: (str(x["period"]), x["parameter"]))
                out["readings"] = rows[:60]
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
