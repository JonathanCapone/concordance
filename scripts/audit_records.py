"""Audit every extracted record for the things that make a number untrustworthy.

Accuracy is measured on a hand-checked gold set of three pages. That is the
honest headline figure, but it says nothing about the thousands of records
extracted from pages nobody has checked. This looks over all of them for defects
that can be found without ground truth:

  unresolved parameter   the parameter table has never seen this name, so the
                         reading cannot join any series and is invisible
  no unit                a bare number that cannot be compared with anything
  unverifiable quote     the source sentence is not on the page it claims
  impossible value       negative concentrations, percentages above 100
  scan damage            a value a power of ten away from its own series

None of these prove a record is wrong. They mark records that cannot be trusted
without a human looking, which is a different and more useful thing than a
confidence score.

    python scripts/audit_records.py
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from concordance.archive import Archive                      # noqa: E402
from concordance.parameters import resolve as resolve_param  # noqa: E402
from concordance.science import find_suspect_readings        # noqa: E402
from concordance.units import parse_unit                     # noqa: E402

SKIP = {"gold_report", "metadata_proposals", "silence_report", "corpus_census"}


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-quotes", action="store_true",
                    help="re-fetch pages and confirm each quote is really on them")
    ap.add_argument("--out", default="data/results/audit.json")
    args = ap.parse_args()

    archive = Archive()
    findings: dict[str, list[dict]] = collections.defaultdict(list)
    total = 0
    page_cache: dict[tuple[str, int], str] = {}

    for path_str in sorted(glob.glob("data/results/*.json")):
        path = Path(path_str)
        if path.stem in SKIP or path.stem == "audit":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload.get("records") or []
        place = payload.get("place", path.stem)
        total += len(records)

        for r in records:
            prov = r.get("provenance") or {}
            tag = {
                "place": place, "period": r.get("period"),
                "parameter": r.get("parameter"), "value": r.get("value"),
                "unit": r.get("unit"), "kind": r.get("kind"),
                "page": prov.get("page"), "identifier": prov.get("identifier"),
            }

            if resolve_param(r.get("parameter") or "", r.get("unit")) is None:
                findings["unresolved_parameter"].append(tag)

            unit = r.get("unit")
            if r.get("kind") in ("observation", "standard", "design"):
                if not unit:
                    findings["no_unit"].append(tag)
                elif parse_unit(unit, parameter=r.get("parameter")) is None:
                    findings["unknown_unit"].append(tag)

            v = r.get("value")
            if isinstance(v, (int, float)):
                if v < 0:
                    findings["negative_value"].append(tag)
                if unit and str(unit).strip() in {"%", "percent"} and v > 100:
                    findings["percentage_over_100"].append(tag)

            if args.verify_quotes:
                ident, page_no = prov.get("identifier"), prov.get("page")
                quote = prov.get("source_text") or ""
                if ident and page_no and quote:
                    key = (ident, page_no)
                    if key not in page_cache:
                        try:
                            pages = {p.page: p.text for p in archive.pages(ident)}
                        except Exception:  # noqa: BLE001
                            pages = {}
                        page_cache[key] = pages.get(page_no, "")
                    if page_cache[key] and norm(quote) not in norm(page_cache[key]):
                        findings["quote_not_on_page"].append(tag)

        # scan-damage check needs the series, so it runs per parameter
        by_param: dict[tuple, list] = collections.defaultdict(list)
        for r in records:
            if r.get("kind") != "observation" or not isinstance(r.get("value"), (int, float)):
                continue
            p = resolve_param(r.get("parameter") or "", r.get("unit"))
            if p is None or not r.get("period"):
                continue
            try:
                year = float(str(r["period"])[:4])
            except ValueError:
                continue
            # Split by STREAM as well as parameter. Influent and effluent BOD are
            # both bod|concentration, and an effluent reading of 8 mg/L against an
            # influent median of 143 looks exactly like a dropped digit. Grouping
            # them together made the scan-damage check fire on the plant working.
            by_param[(place, p.key, r.get("stream") or "unknown")].append(
                (year, float(r["value"]), 0.9)
            )
        for (pl, key, stream), pts in by_param.items():
            for note in find_suspect_readings(sorted(pts)):
                findings["scan_damage"].append({
                    "place": pl, "parameter": f"{key} ({stream})", "note": note,
                })

    print(f"audited {total} records across {len(glob.glob('data/results/*.json'))} files\n")
    order = ["quote_not_on_page", "scan_damage", "percentage_over_100", "negative_value",
             "no_unit", "unknown_unit", "unresolved_parameter"]
    for name in order:
        rows = findings.get(name) or []
        if not rows:
            continue
        pct = len(rows) / total * 100 if total else 0
        print(f"{name:<22} {len(rows):>4}  ({pct:.1f}% of records)")
        for row in rows[:4]:
            if "note" in row:
                print(f"    {row['place']}: {row['note'][:96]}")
            else:
                print(f"    {row['place']} {row.get('period')} "
                      f"{str(row.get('parameter'))[:30]} = {row.get('value')} "
                      f"{row.get('unit') or '(no unit)'}")
        if len(rows) > 4:
            print(f"    ... and {len(rows)-4} more")
        print()

    clean = total - sum(len(v) for v in findings.values())
    print(f"records with no flag at all: {clean}/{total} ({clean/total*100:.0f}%)"
          if total else "no records")

    Path(args.out).write_text(json.dumps({
        "records_audited": total,
        "counts": {k: len(v) for k, v in findings.items()},
        "findings": {k: v[:200] for k, v in findings.items()},
        "note": (
            "A flag does not mean a record is wrong. It marks one that cannot be "
            "trusted without a human looking at the page, which is a different and "
            "more useful thing than a confidence score."
        ),
    }, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
