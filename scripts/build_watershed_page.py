"""Render the downstream network: who was discharging above whom.

Draws each river as a chain of towns ordered by catchment area, so the page reads
the way the water runs. The excluded Sydenham pair is shown too rather than
omitted -- a page that only displays what the method got right teaches nobody
where it fails.

    python scripts/build_watershed_page.py
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from concordance.chrome import ARTIFACT_CSS, masthead          # noqa: E402
from concordance.providers import Fetcher, Registry            # noqa: E402
from concordance.watershed import (                            # noqa: E402
    downstream_links,
    load_stations,
    place_plants,
    who_was_upstream,
)


def build() -> dict:
    reg = Registry.load()
    fetch = Fetcher()
    geo = fetch.fetch(
        reg.providers["eccc-hydrometric-stations"],
        {"PROV_TERR_STATE_LOC": "ON", "limit": "3000", "f": "json"},
    )
    stations = load_stations(geo)

    silence = json.loads(
        Path("data/results/silence_report.json").read_text(encoding="utf-8")
    )

    try:
        from concordance.places import resolve
    except Exception:  # noqa: BLE001
        resolve = None

    plants = []
    unplaced = []
    for m in silence["municipalities"]:
        p = resolve(m["place"], m["last_year"]) if resolve else None
        lat, lon = getattr(p, "lat", None), getattr(p, "lon", None)
        if p and lat and lon:
            plants.append((p.canonical, lat, lon))
        else:
            unplaced.append(m["place"])

    placed = place_plants(plants, stations)
    links, warnings = downstream_links(placed)

    # Group into chains per river, ordered upstream to downstream.
    rivers: dict[str, list] = {}
    for link in links:
        rivers.setdefault(link.watercourse, []).append(link)

    chains = []
    for river, ls in sorted(rivers.items()):
        order: list[str] = []
        for link in ls:
            if link.upstream not in order:
                order.append(link.upstream)
            if link.downstream not in order:
                order.append(link.downstream)
        area = {}
        for link in ls:
            area[link.upstream] = link.upstream_drainage_km2
            area[link.downstream] = link.downstream_drainage_km2
        order.sort(key=lambda t: area.get(t, 0))
        chains.append({
            "river": river,
            "towns": [{"name": t, "area": area.get(t, 0)} for t in order],
            "confidence": [l.confidence for l in ls],
        })

    return {
        "chains": chains,
        "warnings": warnings,
        "n_plants": len(placed),
        "n_on_river": sum(1 for p in placed if p.watercourse),
        "unplaced": unplaced,
        "examples": {
            t: [u["place"] for u in who_was_upstream(links, t)]
            for t in ("Cayuga", "Clarkson", "Chatham")
        },
    }


def render(d: dict) -> str:
    chain_html = []
    for c in d["chains"]:
        max_area = max((t["area"] for t in c["towns"]), default=1) or 1
        steps = []
        for i, t in enumerate(c["towns"]):
            width = 18 + 82 * (t["area"] / max_area)
            steps.append(
                f'<div class="town">'
                f'<div class="bar" style="width:{width:.0f}%"></div>'
                f'<div class="tn">{html.escape(t["name"])}</div>'
                f'<div class="ta">{t["area"]:,.0f} km&sup2; catchment</div>'
                f"</div>"
            )
            if i < len(c["towns"]) - 1:
                steps.append('<div class="arrow">&darr;</div>')
        chain_html.append(
            f'<section><h2>{html.escape(c["river"].title())}</h2>'
            f'<p class="gloss">water runs down the page</p>'
            f'{"".join(steps)}</section>'
        )

    warn_html = "".join(
        f"<li>{html.escape(w)}</li>" for w in d["warnings"]
    ) or "<li>none</li>"

    ex_html = "".join(
        f"<li><strong>{html.escape(t)}</strong> received the discharge of "
        f"{html.escape(', '.join(u)) if u else 'no upstream plant in this set'}</li>"
        for t, u in d["examples"].items() if u
    )

    chrome_css = ARTIFACT_CSS
    head = masthead("Whose effluent was in your water", home="index.html")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Whose effluent was in your water</title>
<style>
{chrome_css}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
 font:16px/1.65 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:760px;margin:0 auto;padding:40px 24px 90px}}
h1{{font-size:30px;font-weight:500;margin:0 0 6px;letter-spacing:-.02em}}
.sub{{color:var(--muted);max-width:64ch;margin:0 0 26px}}
section{{background:var(--panel);border:1px solid var(--line);border-radius:10px;
 padding:20px 22px;margin:22px 0}}
h2{{font-size:17px;font-weight:500;margin:0}}
.gloss{{color:var(--muted);font-size:13px;margin:2px 0 16px}}
.town{{margin:0 0 4px}}
.bar{{height:9px;background:var(--ink);opacity:.28;border-radius:2px}}
.tn{{font-size:15px;margin-top:3px}}
.ta{{font-size:12px;color:var(--muted);font-family:ui-monospace,monospace}}
.arrow{{color:var(--muted);font-size:15px;margin:2px 0 6px}}
ul{{margin:8px 0 0;padding-left:20px;font-size:14px}}
li{{margin-bottom:6px}}
.warn li{{color:var(--warn)}}
.caveat{{border-left:3px solid var(--line);padding-left:16px;color:var(--muted);
 font-size:14px;margin-top:28px;max-width:74ch}}
</style></head><body>
{head}
<main>
<h1>Whose effluent was in your water</h1>
<p class="sub">
  {d['n_on_river']} of {d['n_plants']} Ontario municipal treatment plants placed on a named
  watercourse, then ordered by the catchment area of the nearest river gauge &mdash; which
  necessarily grows downstream. Sewage records come from scanned government reports; river
  gauges from the Water Survey of Canada. Both open, neither requiring a key.
</p>

{''.join(chain_html)}

<section>
  <h2>Read the other way round</h2>
  <p class="gloss">what arrived, rather than what was sent</p>
  <ul>{ex_html}</ul>
</section>

<section>
  <h2>What the method refused to link</h2>
  <p class="gloss">shown because a page that only displays its successes teaches nobody where it fails</p>
  <ul class="warn">{warn_html}</ul>
</section>

<p class="caveat">
  These are inferences, not routed hydrology. A plant is placed at its town's coordinates rather
  than its actual outfall, and rivers are matched by name rather than by basin identifier. Ontario
  has two Sydenham Rivers in unconnected watersheds, and an earlier version of this linked them
  confidently. Before any claim is made about a specific community's water, check it against the
  National Hydro Network.
</p>
</main></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="portal/watershed.html")
    args = ap.parse_args()
    data = build()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size/1024:.0f} KB) — "
          f"{len(data['chains'])} rivers, {len(data['warnings'])} refusals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
