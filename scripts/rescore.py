"""Re-score a saved extraction run without calling a model again.

Extraction is the slow part (minutes per page on a local model), and the scoring
logic changes far more often than the extracted records do. Re-running the model
to test a matcher change would make every harness fix a ten-minute round trip and
would also let model non-determinism leak into what should be a pure measurement
of the scorer.

    python scripts/rescore.py [--report data/results/gold_report.json]
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from groundtruth.models import Provenance, Record       # noqa: E402
from groundtruth.score import Report, load_gold, score_page  # noqa: E402


def records_from_report(path: Path) -> list[Record]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: list[Record] = []
    for d in payload.get("records", []):
        p = d.get("provenance") or {}
        out.append(
            Record(
                kind=d["kind"],
                parameter=d.get("parameter", ""),
                value=d.get("value"),
                unit=d.get("unit"),
                qualifier=d.get("qualifier"),
                stream=d.get("stream", "unknown"),
                place=d.get("place"),
                period=d.get("period"),
                confidence=d.get("confidence", 0.0),
                provenance=Provenance(
                    identifier=p.get("identifier", ""),
                    page=p.get("page"),
                    source_text=p.get("source_text", ""),
                ),
            )
        )
    return out, payload.get("model", "unknown")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default="data/results/gold_report.json")
    ap.add_argument("--gold", default="data/gold/*.json")
    args = ap.parse_args()

    records, model = records_from_report(Path(args.report))
    by_ident: dict[str, list[Record]] = {}
    for r in records:
        if r.provenance:
            by_ident.setdefault(r.provenance.identifier, []).append(r)

    scores = []
    for gold_path in sorted(glob.glob(args.gold)):
        gold = load_gold(gold_path)
        ident = gold["identifier"]
        got_all = by_ident.get(ident, [])
        print(f"\n=== {ident} ===")
        for page_str, entries in gold["pages"].items():
            page_no = int(page_str)
            got = [r for r in got_all if r.provenance and r.provenance.page == page_no]
            s = score_page(entries, got, page_no)
            scores.append(s)
            print(
                f"  page {page_no:>3}  gold {len(entries):>2}  got {len(got):>2}  "
                f"P {s.precision:>5.0%}  R {s.recall:>5.0%}  "
                f"kind {s.kind_accuracy:>4.0%}  stream {s.stream_accuracy:>4.0%}"
            )

    report = Report(scores=scores)
    print("\n" + report.render())
    print(f"\nmodel: {model}  (records re-scored, not re-extracted)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
