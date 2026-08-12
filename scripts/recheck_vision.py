"""Re-score saved vision records against the CURRENT verification rules.

The trial writes every record the model returned, including the ones rejected at
the time. That turned out to matter: the label check demanded a heading appear
as a contiguous string, and a Statistics Canada column heading reads
"CT - SR 135.03" while the OCR of its header row runs "CT - SR CT - SR CT - SR
... 135.02 135.03" -- every part present, none adjacent. Whole pages were thrown
away with entirely correct values on them.

The rules are fixed now. This replays them over what is already on disk, so the
damage can be measured without paying for the pages again -- which is the second
time in this project that keeping the raw output has paid for itself.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from groundtruth.archive import Archive
from groundtruth.models import Provenance, Record
from groundtruth.vision import _label_on_page

TRIAL = Path("data/results/vision_trial_corpus.json")


def main() -> None:
    archive = Archive()
    rows = json.loads(TRIAL.read_text(encoding="utf-8"))
    pages: dict[str, str] = {}

    kept = would_keep = 0
    per_page = []
    for key, row in rows.items():
        if "error" in row:
            continue
        ident, page_no = row["identifier"], row["page"]
        if key not in pages:
            try:
                pages[key] = {p.page: p.text for p in archive.pages(ident)}.get(page_no, "")
            except Exception:  # noqa: BLE001
                pages[key] = ""
        text = pages[key]

        recovered = 0
        # Pages read before the trial started saving rejections carry only a
        # count, so their rejected candidates cannot be replayed and are
        # reported as unrecoverable rather than as zero damage.
        replayable = bool(row.get("rejected")) or not row.get("n_rejected")
        for rec in (row.get("records") or []) + (row.get("rejected") or []):
            rec = rec.get("candidate", rec) if "candidate" in rec else rec
            source = (rec.get("provenance") or {}).get("source_text") or ""
            labels = [p.strip() for p in
                      source.replace("table cell", "").strip(" []").split("/") if p.strip()]
            ok = all(_label_on_page(lab, text) for lab in labels) if labels else True
            candidate = Record(
                kind=rec.get("kind") or "observation",
                parameter=str(rec.get("parameter") or ""),
                value=rec.get("value"), unit=rec.get("unit"),
                confidence=float(rec.get("confidence") or 0.5),
                provenance=Provenance(ident, page_no, source or "x"),
            )
            if ok and not candidate.problems():
                recovered += 1
        kept += row["n_records"]
        would_keep += recovered
        if recovered != row["n_records"] or not replayable:
            per_page.append((key, row["n_records"], recovered,
                             row["n_rejected"], replayable))

    print(f"pages replayed        {len([r for r in rows.values() if 'error' not in r])}")
    print(f"records kept then     {kept}")
    print(f"records kept now      {would_keep}")
    print(f"recovered by the fix  {would_keep - kept}\n")
    blind = [r for r in per_page if not r[4]]
    if blind:
        print(f"  {len(blind)} page(s) were read before rejections were saved.")
        print("  Their discarded candidates cannot be replayed and must be re-read:")
        for key, before, _, rejected, _ in blind:
            print(f"    {key[:44]:44s} kept {before:3d}, rejected {rejected}")
        print()
    for key, before, after, rejected, ok in per_page:
        if ok:
            print(f"  {key[:44]:44s} {before:3d} -> {after:3d}   (rejected {rejected})")


if __name__ == "__main__":
    main()
