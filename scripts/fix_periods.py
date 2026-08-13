"""Anchor bare month names to the year of the report they came from.

The extractor returns "March" or "December 9" when a sentence names a month
without repeating the year. Those parse as no year at all and vanish from every
series without a word, which is the worst way to lose a reading. The report's own
year is known from its Internet Archive item, so the fix is exact rather than a
guess.

    python scripts/fix_periods.py
"""
from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from concordance.archive import Archive  # noqa: E402

YEAR = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")
SKIP = {"gold_report", "metadata_proposals", "silence_report", "corpus_census"}


def main() -> int:
    years = {it["identifier"]: str(it.get("year") or "")
             for it in Archive().load_index()}
    for path_str in sorted(glob.glob("data/results/*.json")):
        path = Path(path_str)
        if path.stem in SKIP:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload.get("records")
        if not records:
            continue
        fixed, orphaned = 0, 0
        for r in records:
            period = str(r.get("period") or "")
            if YEAR.search(period):
                continue
            ident = (r.get("provenance") or {}).get("identifier", "")
            year = years.get(ident, "")
            if not YEAR.search(year):
                orphaned += 1
                continue
            r["period"] = f"{year} {period}".strip() if period else year
            fixed += 1
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{path.name}: anchored {fixed}, still undated {orphaned}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
