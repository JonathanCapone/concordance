"""Re-judge saved table readings against the CURRENT verification rules.

The trial writes every record the model returned, including the ones the
verifier threw out. That has now paid for itself three times, because the
verifier was wrong three times and the model was not:

* a column heading had to appear as a contiguous string, and a Statistics
  Canada header row runs "CT - SR CT - SR CT - SR ... 135.02 135.03" -- every
  part present, none adjacent;
* a page whose OCR was destroyed was allowed to refuse headings it could not
  possibly confirm, which is the exact case the vision path exists for;
* a table cell was required to carry a unit, though its unit lives in a caption
  the model may never have been shown.

Each fix recovered readings that were already on disk. Replaying them costs
nothing; re-reading the pages would have cost about ten minutes each.

    python scripts/recheck_vision.py            # report only
    python scripts/recheck_vision.py --apply    # move recovered readings back
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from concordance.archive import Archive
from concordance.models import Provenance, Record
from concordance.vision import (
    _disambiguate_columns, _label_on_page, _page_can_referee,
)

TRIAL = Path("data/results/vision_trial_corpus.json")


def _labels(source: str) -> list[str]:
    body = str(source or "").replace("table cell", "").strip(" []")
    return [p.strip() for p in body.split("/") if p.strip()]


def _survives(rec: dict, ident: str, page_no: int, text: str, can_referee: bool) -> bool:
    """Would this candidate be kept under today's rules?"""
    source = (rec.get("provenance") or {}).get("source_text") or ""
    if not source:
        source = f"table cell [{rec.get('row_label','')} / {rec.get('column_label','')}]"
    if can_referee:
        if not all(_label_on_page(lab, text) for lab in _labels(source)):
            return False
    candidate = Record(
        kind=rec.get("kind") or "observation",
        parameter=str(rec.get("parameter") or ""),
        value=rec.get("value"),
        unit=rec.get("unit"),
        confidence=float(rec.get("confidence") or 0.5),
        # The path matters: a table cell is exempt from the unit rule because
        # its unit lives in a caption. Rebuilding provenance without it made an
        # earlier version of this script judge every table record as prose and
        # report no change at all.
        provenance=Provenance(ident, page_no, source, path="vision"),
    )
    return not candidate.problems()


def _as_record(cand: dict, ident: str, page_no: int) -> dict:
    """Turn a rejected candidate back into a record the rest of the code reads."""
    source = (cand.get("provenance") or {}).get("source_text") or (
        f"table cell [{cand.get('row_label','')} / {cand.get('column_label','')}]")
    return {
        "kind": cand.get("kind") or "observation",
        "parameter": cand.get("parameter"),
        "value": cand.get("value"),
        "unit": cand.get("unit"),
        "qualifier": cand.get("qualifier"),
        "stream": cand.get("stream") or "unknown",
        "place": cand.get("place"),
        "period": cand.get("period"),
        "confidence": min(0.8, float(cand.get("confidence") or 0.5)),
        "provenance": {
            "identifier": ident, "page": page_no, "source_text": source,
            "path": "vision", "extractor": "recovered-by-recheck",
        },
        "raw": {"row_label": cand.get("row_label"),
                "column_label": cand.get("column_label"),
                "recovered": "kept by a later fix to the verifier"},
    }


def _disambiguated(records: list[dict]) -> list[dict]:
    """Apply today's column rule to records extracted before it existed.

    An expenditure table gives In-House 15, Contracts 100 and Total 115 for one
    year. Sharing a parameter name, they reach the dispute ledger as a
    three-way contradiction about a department's budget. Records read before
    the rule existed never had it applied, so a replay that skipped this would
    report 29 contested slots that the current extractor would not produce.
    """
    as_objects = [
        Record(
            kind=r.get("kind") or "observation",
            parameter=str(r.get("parameter") or ""),
            value=r.get("value"), unit=r.get("unit"),
            confidence=float(r.get("confidence") or 0.5),
            raw=dict(r.get("raw") or {}),
        )
        for r in records
    ]
    _disambiguate_columns(as_objects)
    for original, updated in zip(records, as_objects):
        original["parameter"] = updated.parameter
    return records


def main() -> None:
    apply = "--apply" in sys.argv
    archive = Archive()
    rows = json.loads(TRIAL.read_text(encoding="utf-8"))
    pages: dict[str, str] = {}

    kept = would_keep = moved = 0
    per_page: list[tuple[str, int, int, int, bool]] = []

    for key, row in rows.items():
        if "error" in row:
            continue
        ident, page_no = row["identifier"], row["page"]
        if key not in pages:
            try:
                pages[key] = {p.page: p.text
                              for p in archive.pages(ident)}.get(page_no, "")
            except Exception:  # noqa: BLE001
                pages[key] = ""
        text = pages[key]

        records = row.get("records") or []
        rejected = row.get("rejected") or []
        claimed = [dict(r.get("candidate") or r) for r in rejected] + records
        can_referee = _page_can_referee(claimed, text)

        survivors = [r for r in records
                     if _survives(r, ident, page_no, text, can_referee)]
        recovered, still = [], []
        for rej in rejected:
            cand = rej.get("candidate") or {}
            if _survives(cand, ident, page_no, text, can_referee):
                recovered.append(cand)
            else:
                still.append(rej)

        kept += row["n_records"]
        would_keep += len(survivors) + len(recovered)

        # A page read before rejections were stored carries only a count, so its
        # discarded candidates cannot be replayed. Reported as unrecoverable
        # rather than as zero damage -- those look identical otherwise.
        replayable = bool(rejected) or not row.get("n_rejected")
        if len(survivors) + len(recovered) != row["n_records"] or not replayable:
            per_page.append((key, row["n_records"],
                             len(survivors) + len(recovered),
                             row.get("n_rejected", 0), replayable))

        if apply:
            # Every page, not only the ones with something to recover. The
            # column rule is a current rule too, and the expenditure table that
            # produced 29 contested slots had no rejections at all -- so a
            # version of this that only touched pages with recoveries left the
            # contradiction it was meant to remove.
            row["records"] = _disambiguated(
                survivors + [_as_record(c, ident, page_no) for c in recovered])
            row["rejected"] = still
            row["n_records"] = len(row["records"])
            row["n_rejected"] = len(still)
            moved += len(recovered)

    if apply:
        TRIAL.write_text(json.dumps(rows, indent=2, ensure_ascii=False),
                         encoding="utf-8")
        print(f"moved {moved} recovered readings into records\n")

    live = len([r for r in rows.values() if "error" not in r])
    print(f"pages replayed        {live}")
    print(f"records kept then     {kept}")
    print(f"records kept now      {would_keep}")
    print(f"recovered by the fix  {would_keep - kept}\n")

    blind = [r for r in per_page if not r[4]]
    if blind:
        print(f"  {len(blind)} page(s) were read before rejections were saved.")
        print("  Their discarded candidates cannot be replayed and must be re-read:")
        for key, before, _, rejected_n, _ in blind:
            print(f"    {key[:44]:44s} kept {before:3d}, rejected {rejected_n}")
        print()
    for key, before, after, rejected_n, ok in per_page:
        if ok:
            print(f"  {key[:44]:44s} {before:3d} -> {after:3d}   "
                  f"(rejected {rejected_n})")


if __name__ == "__main__":
    main()
