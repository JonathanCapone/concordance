"""Build a self-contained page showing what stopped being measured.

Data is inlined rather than fetched, so the page opens from the filesystem with
no server and no network -- which matters for showing it on conference wifi, and
means the artifact stays readable long after any host for it goes away.

    python scripts/build_portal.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>What Ontario stopped measuring</title>
<style>
  :root {
    --bg: #fbfaf8; --panel: #fff; --ink: #17150f; --muted: #6b6559;
    --line: #e2ded5; --mark: #17150f; --gap: #d9534f;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #14130f; --panel: #1c1a16; --ink: #f2efe8; --muted: #9b948a;
      --line: #2e2b25; --mark: #f2efe8; --gap: #e0736e;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 40px 24px 80px; background: var(--bg); color: var(--ink);
    font: 16px/1.65 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  main { max-width: 1080px; margin: 0 auto; }
  h1 { font-size: 30px; font-weight: 500; margin: 0 0 6px; letter-spacing: -.02em; }
  .sub { color: var(--muted); max-width: 68ch; margin: 0 0 34px; }
  h2 { font-size: 17px; font-weight: 500; margin: 40px 0 12px; }
  .panel {
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 10px; padding: 18px 20px;
  }
  .scroll { overflow-x: auto; }
  .fab { display: grid; gap: 0; min-width: 720px; }
  .row { display: grid; grid-template-columns: 190px 1fr; align-items: center; height: 9px; }
  .row.head { height: auto; align-items: end; margin-bottom: 8px; }
  .nm {
    font: 8px/9px ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--muted);
    text-align: right; padding-right: 10px; white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis;
  }
  .cells { display: grid; gap: 1px; }
  .c { height: 8px; border-radius: 1px; background: transparent; }
  .c.on { background: var(--mark); opacity: .85; }
  .c.off { background: var(--line); }
  .c.dead { background: var(--gap); opacity: .16; }
  .yr {
    font: 9px/1 ui-monospace, monospace; color: var(--muted); text-align: center;
    writing-mode: vertical-rl; transform: rotate(180deg); height: 30px;
  }
  .yr.big { color: var(--ink); }
  .legend { display: flex; flex-wrap: wrap; gap: 18px; margin-top: 14px;
            font-size: 13px; color: var(--muted); }
  .key { display: flex; align-items: center; gap: 7px; }
  .sw { width: 12px; height: 9px; border-radius: 2px; display: inline-block; }
  table { border-collapse: collapse; width: 100%; font-size: 14px; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); }
  th { font-weight: 500; color: var(--muted); }
  td.num { text-align: right; font-family: ui-monospace, monospace; }
  .verdict { font-size: 15px; margin-top: 14px; }
  .big { font-size: 40px; font-weight: 500; letter-spacing: -.02em; }
  .caveat {
    border-left: 3px solid var(--line); padding: 2px 0 2px 16px;
    color: var(--muted); font-size: 14px; margin-top: 28px; max-width: 74ch;
  }
  a { color: inherit; }
</style>
</head>
<body>
<main>
  <h1>What Ontario stopped measuring</h1>
  <p class="sub">
    Every Ontario municipality that filed a water pollution control plant annual report to the
    provincial government, and the year each one stopped. Built from the Internet Archive Canada
    government publications collection &mdash; __NMUNI__ municipalities, read out of scanned paper.
  </p>

  <div class="panel scroll">
    <div class="fab" id="fab"></div>
  </div>
  <div class="legend">
    <span class="key"><i class="sw" style="background:var(--mark);opacity:.85"></i> filed a report</span>
    <span class="key"><i class="sw" style="background:var(--line)"></i> no report that year</span>
    <span class="key"><i class="sw" style="background:var(--gap);opacity:.16"></i> after this town's last report</span>
  </div>

  <h2>The cliff</h2>
  <div class="panel">
    <div class="big">__CLIFFN__ of __NMUNI__</div>
    <div>municipalities stop reporting in <strong>__CLIFFY__</strong>.</div>
  </div>

  <h2>Is that real, or did the scanning just stop?</h2>
  <div class="panel">
    <p style="margin-top:0;color:var(--muted);font-size:14px;max-width:72ch">
      A whole series vanishing at once usually means a digitisation boundary, not history.
      So: does the rest of the collection also stop in __CLIFFY__?
    </p>
    <table>
      <tr><th>Series in the same collection</th><th style="text-align:right">before</th>
          <th style="text-align:right">after</th><th></th></tr>
      __CONTROL_ROWS__
    </table>
    <p class="verdict">__VERDICT__</p>
  </div>

  <p class="caveat">
    A gap means <em>not digitised</em> or <em>not reported</em> &mdash; those are different claims and
    the data looks the same. The control above separates them for the collection as a whole. It does
    not do so for any individual town, and no single municipality's gap here should be cited as
    evidence that town stopped being monitored.
  </p>
</main>

<script>
const DATA = __DATA__;

const munis = DATA.municipalities;
const first = Math.min(...munis.map(m => m.first_year));
const last  = DATA.horizon;
const years = []; for (let y = first; y <= last; y++) years.push(y);
const cols = `repeat(${years.length}, 1fr)`;
const fab = document.getElementById('fab');

let head = '<div class="row head"><div></div><div class="cells" style="grid-template-columns:' + cols + '">';
years.forEach(y => {
  const show = (y % 5 === 0) || y === first || y === DATA.largest_simultaneous_stop.year;
  const big = y === DATA.largest_simultaneous_stop.year ? ' big' : '';
  head += `<div class="yr${big}">${show ? y : ''}</div>`;
});
fab.insertAdjacentHTML('beforeend', head + '</div></div>');

// Ordered by when each town started, then by how long it lasted: the shape reads
// as a staircase that stops dead at one wall.
munis.slice().sort((a, b) =>
  a.first_year - b.first_year || b.reported_years.length - a.reported_years.length
).forEach(m => {
  const has = new Set(m.reported_years);
  let cells = '';
  years.forEach(y => {
    const cls = has.has(y) ? 'on' : (y > m.last_year ? 'dead' : 'off');
    cells += `<div class="c ${cls}" title="${m.place} — ${y}${has.has(y) ? ': report filed' : ''}"></div>`;
  });
  fab.insertAdjacentHTML('beforeend',
    `<div class="row"><div class="nm" title="${m.place}">${m.place}</div>` +
    `<div class="cells" style="grid-template-columns:${cols}">${cells}</div></div>`);
});
</script>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/results/silence_report.json")
    ap.add_argument("--out", default="portal/silence.html")
    args = ap.parse_args()

    payload = json.loads(Path(args.data).read_text(encoding="utf-8"))
    stop = payload["largest_simultaneous_stop"]

    rows = []
    for c in payload["digitisation_control"]:
        grew = c["from_cliff_onward"] > c["before"] * 0.5
        rows.append(
            f'<tr><td>{c["series"]}</td>'
            f'<td class="num">{c["before"]:,}</td>'
            f'<td class="num">{c["from_cliff_onward"]:,}</td>'
            f'<td>{"keeps going" if grew else "also stops"}</td></tr>'
        )

    verdict = (
        "The archive kept growing while this one series died. "
        "<strong>The silence is real.</strong>"
        if payload.get("control_verdict") == "real"
        else "The whole collection thins at the same time. "
        "<strong>This is probably a digitisation boundary, not history.</strong>"
    )

    html = (
        TEMPLATE.replace("__DATA__", json.dumps(payload))
        .replace("__NMUNI__", str(payload["n_municipalities"]))
        .replace("__CLIFFN__", str(stop["municipalities"]))
        .replace("__CLIFFY__", str(stop["year"]))
        .replace("__CONTROL_ROWS__", "\n      ".join(rows))
        .replace("__VERDICT__", verdict)
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out}  ({out.stat().st_size / 1024:.0f} KB, self-contained)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
