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
    scored: list[str] = []
    skipped: list[str] = []
    for gold_path in sorted(glob.glob(args.gold)):
        gold = load_gold(gold_path)
        ident = gold["identifier"]
        got_all = by_ident.get(ident, [])
        # A gold document the saved run never touched is not a document the
        # extractor failed on. Scoring it turned every one of its entries into a
        # miss and dropped published recall from 82.5% to 70.6% the moment a
        # second gold document was added -- punishing the run for a page it was
        # never asked to read.
        #
        # This is the mirror of the stream-accuracy bug fixed alongside it: one
        # control flattered itself on an empty page and the other convicted
        # itself. Both come from treating "no data" as a score.
        if not got_all:
            skipped.append(ident)
            continue
        scored.append(ident)
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
    if skipped:
        print(f"\nNOT SCORED -- the saved run contains no records for "
              f"{len(skipped)} gold document(s):")
        for ident in skipped:
            print(f"  {ident}")
        print("Run scripts/run_gold.py to extract them; until then this figure")
        print("describes the documents listed above it and no others.")

    # Write the corrected totals back. Without this the report file keeps
    # whatever the scorer produced when extraction last ran, and everything
    # reading it -- the portal, the live server -- serves a stale accuracy
    # figure. That already happened: the running map advertised 49% precision
    # for hours after the harness bug causing it had been found and fixed.
    path = Path(args.report)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["totals"] = report.totals
    payload["rescored"] = True
    # Which documents the figure actually describes. Without this the file says
    # "precision 90.6%" and cannot say of what.
    payload["scored_documents"] = scored
    payload["gold_documents_not_scored"] = skipped
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"updated totals in {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
