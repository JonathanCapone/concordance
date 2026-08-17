"""Render one town's recovered record as a page you can check.

The point of this page is not the chart. It is that every single number on it
resolves to the scanned page it was read from, with the exact sentence quoted, so
a reader can disagree with it in about a minute. A measurement recovered by a
language model from a sixty-year-old scan has no authority on its own; it earns
authority by being trivially falsifiable.

Charts are drawn as inline SVG rather than by a plotting library so the page stays
self-contained and opens from the filesystem with no network.

    python scripts/build_town_page.py --file data/results/owen-sound.json
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from concordance.chrome import ARTIFACT_CSS, masthead  # noqa: E402
from concordance.models import Provenance, Record   # noqa: E402
from concordance.science import series_from_records, trend  # noqa: E402

W, H = 720, 200
PAD_L, PAD_R, PAD_T, PAD_B = 54, 18, 18, 30


def load(path: Path) -> tuple[list[Record], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for d in payload.get("records", []):
        p = d.get("provenance") or {}
        out.append(
            Record(
                kind=d["kind"], parameter=d.get("parameter", ""), value=d.get("value"),
                unit=d.get("unit"), qualifier=d.get("qualifier"),
                stream=d.get("stream", "unknown"), place=d.get("place"),
                facility=d.get("facility"),
                period=d.get("period"), confidence=d.get("confidence", 0.0),
                provenance=Provenance(
                    identifier=p.get("identifier", ""), page=p.get("page"),
                    source_text=p.get("source_text", ""),
                ),
            )
        )
    return out, payload.get("place", "?")


def chart(points, unit: str) -> str:
    """Line chart with a confidence-scaled marker per reading.

    Marker opacity tracks reading confidence, so a series carried by barely
    legible scans looks faint rather than authoritative.
    """
    if len(points) < 2:
        return ""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if y1 == y0:
        y0, y1 = y0 - 1, y1 + 1
    pad = (y1 - y0) * 0.15
    y0, y1 = y0 - pad, y1 + pad

    def px(x): return PAD_L + (x - x0) / max(1e-9, x1 - x0) * (W - PAD_L - PAD_R)
    def py(y): return PAD_T + (1 - (y - y0) / (y1 - y0)) * (H - PAD_T - PAD_B)

    parts = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img">']
    # horizontal guides
    for i in range(4):
        v = y0 + (y1 - y0) * i / 3
        y = py(v)
        parts.append(f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W-PAD_R}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{PAD_L-8}" y="{y+3:.1f}" class="ax" text-anchor="end">{v:.4g}</text>')
    # the line
    d = " ".join(f"{'M' if i == 0 else 'L'}{px(x):.1f},{py(y):.1f}"
                 for i, (x, y, _) in enumerate(points))
    parts.append(f'<path d="{d}" class="line"/>')
    # points, opacity by reading confidence
    for x, y, c in points:
        op = 0.35 + 0.65 * max(0.0, min(1.0, c))
        parts.append(
            f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="4" class="pt" '
            f'opacity="{op:.2f}"><title>{int(x)}: {y:.4g} {html.escape(unit)} '
            f'(reading confidence {c:.2f})</title></circle>'
        )
    for x in xs:
        parts.append(f'<text x="{px(x):.1f}" y="{H-8}" class="ax" text-anchor="middle">{int(x)}</text>')
    parts.append("</svg>")
    return "".join(parts)


TARGETS = [
    ("BOD removal", None, "how much oxygen-demanding waste the plant removed"),
    ("suspended solids removal", None, "how much solid matter the plant removed"),
    ("BOD", "effluent", "what the town discharged"),
    ("suspended solids", "effluent", "solids discharged"),
    ("BOD", "influent", "what arrived at the plant"),
    ("flow", None, "how much sewage passed through"),
]


def accuracy_sentence(report: str | Path = "data/results/gold_report.json") -> str:
    """The measured accuracy, read from the file that holds it.

    This sentence used to be typed into the template. It said 88% precision for
    long enough that the number moved twice underneath it -- and a page whose
    whole argument is "check this against the scan" cannot be the last place in
    the repository still quoting a figure from memory.

    Says which documents the figure covers, because after a second gold document
    was added the totals described one of them and not the other.
    """
    try:
        payload = json.loads(Path(report).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return ("Measured accuracy is published in data/results/gold_report.json; "
                "this build could not read it.")
    totals = payload.get("totals") or {}
    p_ = totals.get("precision")
    r_ = totals.get("recall")
    if p_ is None or r_ is None:
        return "Measured accuracy is published in data/results/gold_report.json."
    docs = payload.get("scored_documents") or []
    scope = (f" on {len(docs)} hand-checked document{'s' if len(docs) != 1 else ''}"
             if docs else "")
    return (f"Measured accuracy against hand-checked ground truth{scope} is "
            f"{p_:.1%} precision and {r_:.1%} recall.")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="data/results/owen-sound.json")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    path = Path(args.file)
    records, place = load(path)
    # One page per facility. A sewage plant's effluent and a water supply
    # system's tap water are opposite measurements and must not share a chart.
    import collections
    facilities = collections.Counter(r.facility or "unclassified" for r in records)
    main = facilities.most_common(1)[0][0] if facilities else None
    if len(facilities) > 1:
        records = [r for r in records if (r.facility or "unclassified") == main]
    obs = [r for r in records if r.kind == "observation"]
    out_path = Path(args.out or f"portal/{path.stem}.html")

    years = sorted({int(str(r.period)[:4]) for r in records
                    if r.period and str(r.period)[:4].isdigit()})
    blocks = []

    for param, stream, gloss in TARGETS:
        s = series_from_records(obs, parameter=param, stream=stream)
        if len(s) < 2:
            continue
        label = param + (f" ({stream})" if stream else "")
        t = trend(s.points)
        notes = "".join(f'<li class="assume">assumed: {html.escape(a)}</li>' for a in s.assumptions)
        notes += "".join(f'<li class="reject">rejected: {html.escape(r)}</li>' for r in s.rejected)
        verdict = html.escape(t.describe()) if t.ok else html.escape(f"no trend: {t.reason}")

        rows = []
        for y, v, c in s.points:
            # The record that produced this point, carried out of
            # series_from_records. This used to search `obs` for ANY observation
            # from the same year, which is how the shipped Owen Sound page came
            # to show twelve of its thirteen numbers beside a sentence that does
            # not contain them -- a flow of 2.1 million gallons captioned with
            # "The total operating cost for treating 1475 million gallons of
            # sewage in 1969 was $53, 549. 66." under a heading promising every
            # number is linked to its scan.
            src = s.sources.get(y)
            if src and src.provenance:
                rows.append(
                    f'<tr><td class="num">{int(y)}</td><td class="num">{v:.4g}</td>'
                    f'<td class="num">{c:.2f}</td>'
                    f'<td class="q">&ldquo;{html.escape(src.provenance.source_text[:150])}&rdquo;</td>'
                    f'<td><a href="{src.provenance.page_url}" target="_blank" rel="noopener">'
                    f'scan p{src.provenance.page}</a></td></tr>'
                )
        blocks.append(f"""
  <section>
    <h2>{html.escape(label)}</h2>
    <p class="gloss">{html.escape(gloss)}{f' &middot; {html.escape(s.unit)}' if s.unit else ''}</p>
    {chart(s.points, s.unit)}
    <p class="verdict">{verdict}</p>
    {f'<ul class="notes">{notes}</ul>' if notes else ''}
    <table>
      <tr><th>year</th><th>value</th><th>conf.</th><th>read from</th><th>check it</th></tr>
      {''.join(rows)}
    </table>
  </section>""")

    body = "".join(blocks) or (
        '<section><p class="gloss">No parameter yet has two comparable years. '
        "Extraction may still be running.</p></section>"
    )

    accuracy_text = accuracy_sentence()
    chrome_css = ARTIFACT_CSS
    head = masthead(html.escape(place), home="index.html")
    html_doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(place)} &mdash; what the record says</title>
<style>
{chrome_css}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
     font:16px/1.65 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:820px;margin:0 auto;padding:40px 24px 90px}}
h1{{font-size:30px;font-weight:500;margin:0 0 6px;letter-spacing:-.02em}}
.sub{{color:var(--muted);margin:0 0 8px;max-width:66ch}}
section{{background:var(--panel);border:1px solid var(--line);border-radius:10px;
        padding:20px 22px;margin:26px 0}}
h2{{font-size:18px;font-weight:500;margin:0 0 2px}}
.gloss{{color:var(--muted);font-size:14px;margin:0 0 14px}}
.chart{{width:100%;height:auto;display:block;margin:4px 0 10px}}
.grid{{stroke:var(--line);stroke-width:1}}
.line{{fill:none;stroke:var(--accent);stroke-width:1.6;opacity:.75}}
.pt{{fill:var(--accent)}}
.ax{{font:10px ui-monospace,monospace;fill:var(--muted)}}
.verdict{{font-size:14px;margin:6px 0 0}}
.notes{{list-style:none;padding:0;margin:10px 0 0;font-size:13px}}
.assume{{color:var(--warn)}} .reject{{color:var(--bad)}}
table{{border-collapse:collapse;width:100%;font-size:13px;margin-top:14px}}
th,td{{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{font-weight:500;color:var(--muted)}}
td.num{{text-align:right;font-family:ui-monospace,monospace;white-space:nowrap}}
td.q{{color:var(--muted);font-style:italic}}
a{{color:inherit}}
.caveat{{border-left:3px solid var(--line);padding-left:16px;color:var(--muted);
        font-size:14px;margin-top:30px;max-width:74ch}}
</style></head><body>
{head}
<main>
<h1>{html.escape(place)}</h1>
<p class="sub">
  {html.escape(str(main or "")).replace("_", " ")}.
  Recovered from {len(years)} scanned annual reports
  {f'({min(years)}&ndash;{max(years)})' if years else ''} filed with the Ontario government.
  {len(records)} readings; {len(obs)} of them measurements rather than design specifications.
</p>
<p class="sub">
  <strong>Every number here links to the page it was read from.</strong> None of it should be
  believed on the strength of this page alone.
</p>
{body}
<p class="caveat">
  These values were read out of OCR'd scans by a language model, not transcribed by a person.
  {accuracy_text} Reading confidence is shown per point and controls how solid each
  marker appears. Where a series changes units or method mid-run, the affected readings are
  rejected and listed rather than converted.
</p>
</main></body></html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_doc, encoding="utf-8")
    print(f"wrote {out_path}  ({out_path.stat().st_size/1024:.0f} KB) — "
          f"{len(blocks)} series, {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
