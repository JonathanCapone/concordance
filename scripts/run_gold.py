"""Extract the gold-set pages and score against hand-checked ground truth.

This is the gate the project turns on. Run it before claiming any accuracy
number, and publish whatever it says -- including a bad result.

    python scripts/run_gold.py [--model gemma4:26b] [--gold data/gold/*.json]
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from groundtruth.archive import Archive           # noqa: E402
from groundtruth.extract import OllamaClient, extract_prose  # noqa: E402
from groundtruth.score import Report, load_gold, score_page  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma4:12b")
    ap.add_argument("--gold", default="data/gold/*.json")
    ap.add_argument("--out", default="data/results")
    ap.add_argument("--timeout", type=float, default=1800.0)
    args = ap.parse_args()

    archive = Archive()
    client = OllamaClient(model=args.model, timeout=args.timeout)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_scores = []
    everything = []

    for gold_path in sorted(glob.glob(args.gold)):
        gold = load_gold(gold_path)
        ident = gold["identifier"]
        print(f"\n=== {ident} — {gold.get('title','')[:60]} ===", flush=True)
        pages = {p.page: p for p in archive.pages(ident)}

        for page_no_str, entries in gold["pages"].items():
            page_no = int(page_no_str)
            page = pages.get(page_no)
            if page is None:
                print(f"  page {page_no}: NOT FOUND in parsed pages", flush=True)
                continue

            t0 = time.time()
            result = extract_prose(
                page,
                client=client,
                title=gold.get("title", ""),
                publisher=gold.get("publisher", ""),
                year=str(gold.get("year", "")),
            )
            elapsed = time.time() - t0

            score = score_page(entries, result.records, page_no)
            all_scores.append(score)
            everything.extend(result.records)

            print(
                f"  page {page_no:>3}  {elapsed:>5.0f}s  "
                f"kept {result.kept:>2} / rejected {len(result.rejected):>2}  "
                f"P {score.precision:.0%}  R {score.recall:.0%}  "
                f"kind {score.kind_accuracy:.0%}  stream {score.stream_accuracy:.0%}",
                flush=True,
            )
            for why in {r["why"] for r in result.rejected}:
                n = sum(1 for r in result.rejected if r["why"] == why)
                print(f"       rejected x{n}: {why}", flush=True)

    report = Report(scores=all_scores)
    print("\n" + report.render())

    (out_dir / "gold_report.json").write_text(
        json.dumps(
            {
                "model": client.name,
                "totals": report.totals,
                "records": [r.to_dict() for r in everything],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {out_dir / 'gold_report.json'}  ({len(everything)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
