"""Score the in-browser reader's output against the hand-read gold pages.

    python scripts/bench_browser_reader.py       # build the page
    # run it in a browser, copy window._bench to records.json
    python scripts/score_browser_bench.py records.json

Uses `concordance.score` -- the same scorer that produced the installed
reader's published figures -- so the two numbers are comparable. Nothing here
re-implements matching.

Two scores are reported, because a browser contribution is not the model's raw
output:

  as published   only records that passed the page's own evidence checks, which
                 is what a browser actually sends to a Concordance site
  model output   every record the model produced, which shows what the checks
                 cost in recall and buy in precision

The compact browser instructions do not ask for `stream`, so every browser
record carries stream="unknown". Stream accuracy is therefore reported as
not attempted rather than as a score: influent versus effluent has to come
from the installed reader or a person, and saying so is the point.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from concordance.models import Provenance, Record   # noqa: E402
from concordance.score import Report, load_gold, score_page  # noqa: E402


def as_records(entries: list[dict], identifier: str, page: int) -> list[Record]:
    """Browser JSON -> the Record shape the scorer expects."""
    out = []
    for e in entries:
        value = e.get("value")
        if isinstance(value, str):
            try:
                value = float(value)
            except ValueError:
                value = None
        if value is not None and not isinstance(value, (int, float)):
            value = None
        out.append(Record(
            kind=str(e.get("kind") or "observation"),
            parameter=str(e.get("parameter") or ""),
            value=value,
            unit=(e.get("unit") or None),
            # The compact prompt never proposes one; recorded honestly.
            stream="unknown",
            provenance=Provenance(
                identifier=identifier,
                page=page,
                source_text=str(e.get("source_text") or ""),
                extractor="browser",
            ),
        ))
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    bench = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

    gold_by_id = {}
    for path in sorted(Path("data/gold").glob("*.json")):
        gold = load_gold(path)
        gold_by_id[gold["identifier"]] = gold

    published, everything = [], []
    rows = []

    for page_result in bench.get("pages", []):
        ident, page_no = page_result["identifier"], int(page_result["page"])
        gold = gold_by_id.get(ident)
        if gold is None:
            print(f"no gold for {ident}; skipped")
            continue
        entries = gold["pages"].get(str(page_no)) or gold["pages"].get(page_no)
        if not entries:
            print(f"no gold entries for {ident} p.{page_no}; skipped")
            continue

        got = page_result.get("records", [])
        kept = [r for r in got if r.get("passed")]

        s_pub = score_page(entries, as_records(kept, ident, page_no), page_no)
        s_all = score_page(entries, as_records(got, ident, page_no), page_no)
        published.append(s_pub)
        everything.append(s_all)
        rows.append({
            "identifier": ident, "page": page_no,
            "gold_values": len(entries),
            "produced": len(got), "published": len(kept),
            "seconds": page_result.get("seconds"),
            "as_published": {"precision": s_pub.precision, "recall": s_pub.recall,
                             "kind_accuracy": s_pub.kind_accuracy,
                             "matched": len(s_pub.matches),
                             "missed": len(s_pub.missed),
                             "spurious": len(s_pub.spurious)},
            "model_output": {"precision": s_all.precision, "recall": s_all.recall,
                             "matched": len(s_all.matches),
                             "spurious": len(s_all.spurious)},
        })

    pub, allr = Report(scores=published), Report(scores=everything)

    print("\n=== AS PUBLISHED (records that passed the page's checks) ===")
    print(pub.render())
    print("\n=== MODEL OUTPUT (everything the model produced) ===")
    print(allr.render())
    print("\nper page:")
    print(f"  {'document':34s} {'pg':>3s} {'gold':>5s} {'made':>5s} {'sent':>5s} "
          f"{'P':>6s} {'R':>6s}")
    for r in rows:
        p = r["as_published"]
        print(f"  {r['identifier'][:34]:34s} {r['page']:3d} {r['gold_values']:5d} "
              f"{r['produced']:5d} {r['published']:5d} "
              f"{p['precision']:6.0%} {p['recall']:6.0%}")

    out = {
        "model": bench.get("model"),
        "engine": bench.get("engine"),
        "note": ("The in-browser reader measured against the same hand-read "
                 "gold pages as the installed reader, scored by the same "
                 "scorer. 'as_published' is what a browser sends after its own "
                 "evidence checks; 'model_output' is everything the model "
                 "produced. The compact browser instructions do not ask for "
                 "stream, so stream accuracy is not attempted."),
        "stream_attempted": False,
        "as_published": {
            "precision": pub.totals.get("precision"),
            "recall": pub.totals.get("recall"),
            "kind_accuracy": pub.totals.get("kind_accuracy"),
            **{k: v for k, v in pub.totals.items()
               if k in ("matched", "missed", "spurious")},
        },
        "model_output": {
            "precision": allr.totals.get("precision"),
            "recall": allr.totals.get("recall"),
            **{k: v for k, v in allr.totals.items()
               if k in ("matched", "missed", "spurious")},
        },
        "pages": rows,
    }
    dest = Path("data/results/browser_gold_report.json")
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
