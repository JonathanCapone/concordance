"""Re-file readings whose sentence names a different year than they were given.

A report compares two years in one sentence and states a number for each:

    "The average BOD removal efficiency was 94% in 1969 compared with only
     89% in 1968."

Both values were filed under 1969, so Brantford's published BOD-removal series
read 89% for a year whose page says 94% -- the number the README leads with,
wrong by the width of one sentence.

`dating.year_for_reading` decides which year a sentence attaches to a given
number, and abstains unless the sentence names two years AND frames them as a
comparison. Across the whole corpus it abstains on 1,387 records, agrees with
the extractor on 13, and disagrees on 1. That ratio is the point: a repair that
also "fixes" correct records is worse than no repair, so the agreement count is
the real test and it is checked here every run.

Run with --apply to write. Without it, nothing is touched.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from concordance.dating import year_for_reading

SKIP = {"gold_report", "metadata_proposals", "silence_report", "corpus_census"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/results")
    ap.add_argument("--apply", action="store_true",
                    help="write the corrections; without it this only reports")
    args = ap.parse_args()

    agreed = abstained = 0
    changed: list[tuple[str, str, int, object, str, str]] = []

    for path in sorted(Path(args.dir).glob("*.json")):
        if path.stem in SKIP:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload.get("records") or []
        touched = False

        for r in records:
            quote = (r.get("provenance") or {}).get("source_text") or ""
            said = year_for_reading(quote, r.get("value"))
            if said is None:
                abstained += 1
                continue
            current = str(r.get("period") or "")[:4]
            if current == str(said):
                agreed += 1
                continue

            changed.append((path.name, current, said, r.get("value"),
                            str(r.get("parameter") or ""), quote[:96]))
            if args.apply:
                # The period is replaced, not annotated. A reading filed under
                # the wrong year is not a disputed reading -- the sentence says
                # plainly which year it belongs to, and the record keeps that
                # sentence, so anyone can check the correction the same way it
                # was made.
                r["period"] = said
                touched = True

        if touched:
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                            encoding="utf-8")

    print(f"abstained {abstained}   agreed with the extractor {agreed}   "
          f"{'changed' if args.apply else 'would change'} {len(changed)}")
    for name, cur, new, val, param, quote in changed:
        print(f"\n  [{name}] {val} {param[:30]}   {cur} -> {new}")
        print(f"       {quote!r}")

    if changed and not args.apply:
        print("\nNothing written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
