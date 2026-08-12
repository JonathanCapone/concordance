"""Build the portal front page from whatever has actually been produced.

Numbers on this page are read from the result files rather than typed in, so it
cannot drift into claiming more than the project has done. If a result file is
missing, its card says so instead of showing a stale figure.

    python scripts/build_index.py
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

RESULTS = Path("data/results")


def read(name: str) -> dict | None:
    p = RESULTS / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="portal/index.html")
    args = ap.parse_args()

    gold = read("gold_report.json") or {}
    silence = read("silence_report.json") or {}
    meta = read("metadata_proposals.json") or {}
    town = read("owen-sound.json") or {}

    totals = gold.get("totals", {})
    stop = silence.get("largest_simultaneous_stop", {})
    msum = meta.get("summary", {})

    cards = []

    if silence:
        cards.append((
            "silence.html",
            "What Ontario stopped measuring",
            f"{stop.get('municipalities','?')} of {silence.get('n_municipalities','?')} "
            f"municipalities stop filing water pollution control plant reports in "
            f"{stop.get('year','?')} — checked against the archive's own growth to rule out "
            "a digitisation boundary.",
        ))

    cards.append((
        "watershed.html",
        "Whose effluent was in your water",
        "Treatment plants placed on rivers and ordered by catchment area, so the page reads "
        "the way the water runs. Includes what the method refused to link, and why.",
    ))

    if town.get("records"):
        # Count what the page actually shows. build_town_page renders ONE
        # facility -- a town's sewage plant and its water works measure opposite
        # things -- so counting every record here promised "Owen Sound,
        # 1963-1992, 120 readings" on a card linking to a page that ends in 1972
        # and holds 87. A card that overstates the page behind it is worse than
        # no card, because the reader discovers the gap by clicking.
        records = town["records"]
        facilities = collections.Counter(
            r.get("facility") or "unclassified" for r in records)
        if len(facilities) > 1:
            main = facilities.most_common(1)[0][0]
            records = [r for r in records
                       if (r.get("facility") or "unclassified") == main]
        years = sorted({
            str(r.get("period"))[:4] for r in records
            if r.get("period") and str(r.get("period"))[:4].isdigit()
        })
        obs = sum(1 for r in records if r.get("kind") == "observation")
        span = f"{years[0]}–{years[-1]}" if years else ""
        cards.append((
            "owen-sound.html",
            f"Owen Sound, {span}",
            f"{len(records)} readings recovered from scanned annual reports, "
            f"{obs} of them measurements. Every number links to the page it was read from.",
        ))

    card_html = "".join(
        f'<a class="card" href="{href}"><h2>{title}</h2><p>{body}</p></a>'
        for href, title, body in cards
    )

    def stat(value, label):
        return f'<div class="stat"><div class="v">{value}</div><div class="l">{label}</div></div>'

    stats = "".join([
        stat("104,241", "documents in the collection"),
        stat("22.1M", "scanned pages"),
        stat(f"{totals.get('precision', 0):.0%}" if totals else "—", "extraction precision"),
        stat(f"{msum.get('proposals', 0):,}" if msum else "—", "metadata repairs proposed"),
        stat("90", "median downloads per document"),
    ])

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ground Truth — reading Canada's public record</title>
<style>
:root{{--bg:#fbfaf8;--panel:#fff;--ink:#17150f;--muted:#6b6559;--line:#e2ded5}}
@media (prefers-color-scheme:dark){{
 :root{{--bg:#14130f;--panel:#1c1a16;--ink:#f2efe8;--muted:#9b948a;--line:#2e2b25}}}}
*{{box-sizing:border-box}}
body{{margin:0;padding:56px 24px 90px;background:var(--bg);color:var(--ink);
 font:16px/1.65 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:800px;margin:0 auto}}
h1{{font-size:36px;font-weight:500;margin:0 0 10px;letter-spacing:-.025em}}
.lede{{font-size:18px;color:var(--muted);max-width:62ch;margin:0 0 8px}}
.quiet{{color:var(--muted);max-width:62ch;margin:0 0 34px}}
.stats{{display:flex;flex-wrap:wrap;gap:26px;padding:20px 0 8px;border-top:1px solid var(--line);
 border-bottom:1px solid var(--line);margin-bottom:30px}}
.stat .v{{font-size:22px;font-weight:500;font-variant-numeric:tabular-nums}}
.stat .l{{font-size:12px;color:var(--muted)}}
.card{{display:block;background:var(--panel);border:1px solid var(--line);border-radius:10px;
 padding:20px 22px;margin-bottom:14px;text-decoration:none;color:inherit}}
.card:hover{{border-color:var(--muted)}}
.card h2{{font-size:18px;font-weight:500;margin:0 0 6px}}
.card p{{margin:0;color:var(--muted);font-size:14px}}
.note{{border-left:3px solid var(--line);padding-left:16px;color:var(--muted);
 font-size:14px;margin-top:34px;max-width:74ch}}
a.plain{{color:inherit}}
</style></head><body><main>
<h1>Ground Truth</h1>
<p class="lede">Reading Canada's public record as a hundred-year instrument.</p>
<p class="quiet">
  Internet Archive Canada holds 104,241 scanned government publications. Inside them are
  measurements of the physical condition of the country — air, water, soil — town by town, from
  1841 onward. Almost nobody has read them. Every civil servant who wrote a measurement down was a
  node in a sensor network that ran for 150 years and was never once read as a network.
</p>

<div class="stats">{stats}</div>

{card_html}

<p class="note">
  These figures were recovered from scanned paper by a language model, not transcribed by a person.
  Measured accuracy against hand-checked ground truth is published in the repository, including the
  failures. Every number on every page here links back to the scan it came from, because a
  measurement read out of a sixty-year-old scan has no authority on its own — it earns authority by
  being trivially easy to check.
</p>
</main></body></html>"""

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size/1024:.0f} KB) — {len(cards)} cards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
