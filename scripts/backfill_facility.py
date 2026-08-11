"""Stamp `facility` onto records extracted before that field existed.

Cheaper and more honest than re-extracting: every record already carries the
Internet Archive identifier it came from, and the collection index already has
that item's title, so the facility can be derived exactly rather than guessed.

    python scripts/backfill_facility.py --file data/results/owen-sound.json
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from groundtruth.archive import Archive               # noqa: E402
from groundtruth.parameters import facility_of        # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="data/results/*.json")
    args = ap.parse_args()

    archive = Archive()
    titles = {it["identifier"]: str(it.get("title", "")) for it in archive.load_index()}

    skip = {"gold_report", "metadata_proposals", "silence_report", "corpus_census"}
    for path_str in sorted(glob.glob(args.file)):
        path = Path(path_str)
        if path.stem in skip:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload.get("records")
        if not records:
            continue

        stamped = 0
        counts: collections.Counter = collections.Counter()
        for r in records:
            if r.get("facility"):
                counts[r["facility"]] += 1
                continue
            ident = (r.get("provenance") or {}).get("identifier")
            facility = facility_of(titles.get(ident, ""))
            if facility:
                r["facility"] = facility
                stamped += 1
            counts[facility or "unclassified"] += 1

        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{path.name}: stamped {stamped} of {len(records)}")
        for name, n in counts.most_common():
            print(f"    {n:>4}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
