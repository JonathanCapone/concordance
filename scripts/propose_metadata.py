"""Produce a reviewable metadata-repair diff for the whole collection.

Output is a proposal, never an edit. Nothing in this project writes to anyone
else's catalogue, and the file is structured so a librarian can accept the
deterministic corrections in bulk and look at the inferred ones individually.

    python scripts/propose_metadata.py --out data/results/metadata_proposals.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from concordance.archive import Archive      # noqa: E402
from concordance.repair import repair        # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/results/metadata_proposals.json")
    ap.add_argument("--min-confidence", type=float, default=0.4)
    args = ap.parse_args()

    archive = Archive()
    items = archive.load_index()
    report = repair(items, min_confidence=args.min_confidence)
    summary = report.summary()

    deterministic = [p for p in report.proposals if p.confidence >= 0.999]
    inferred = [p for p in report.proposals if p.confidence < 0.999]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "collection": archive.collection,
                "items_examined": summary["items_examined"],
                "note": (
                    "Proposals, not edits. 'deterministic' entries are exact "
                    "mappings of existing values to ISO 639-2 and involve no "
                    "guessing. 'inferred' entries are recovered from title or "
                    "date text and carry a confidence; each should be reviewed. "
                    "'unresolved_language_values' are values this pass refused "
                    "to interpret, and are reported because they are evidence of "
                    "catalogue defects rather than noise to discard."
                ),
                "summary": summary,
                "deterministic": [p.to_dict() for p in deterministic],
                "inferred": [p.to_dict() for p in inferred],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"examined {summary['items_examined']:,} items")
    print(f"  deterministic corrections : {len(deterministic):,}")
    print(f"  inferred (needs review)   : {len(inferred):,}")
    print(f"  refused to interpret      : {len(summary['unresolved_language_values'])} distinct values")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
