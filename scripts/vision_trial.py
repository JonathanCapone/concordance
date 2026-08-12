"""Measure the vision path across the corpus, not on one lucky page.

The single-page proof (Brantford 1962 p15) showed qwen3.6 recovering all twelve
values that survived in the OCR, and 27 records from a page whose text layer is
unusable. Two numbers were then carried into planning that only one page
supports: **27 records per table page**, and **28.3 minutes per page**. The first
decides what share of the archive's measurements live behind the vision path --
and therefore how much of this work contributors can do at all. The second was a
cold start and is probably wrong.

So this reads table-routed pages from many kinds of document, and reports both
with a spread rather than a point.

**How a fabricated table is caught without a human reading 30 scans.** Two
automatic controls, neither sufficient alone:

* *values in OCR* -- the share of returned numbers that appear somewhere in the
  page's own text layer. High is strong evidence of reading. Low is NOT proof of
  invention, because the OCR is often destroyed, and saying otherwise would
  convict the model of the scanner's crime. Reported per page so the two cases
  can be told apart by looking.
* *labels on page* -- `vision.extract_table` already rejects a record whose
  claimed row or column heading shares no token with the page. The count of
  rejections is a fabrication signal in its own right and is recorded here.

Resumable, and writes after every page: at half an hour a page this will not
finish in one sitting, and a run that loses everything on interruption is a run
nobody will start.
"""

from __future__ import annotations

import json
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from groundtruth.archive import Archive
from groundtruth.router import Path as RPath, route
from groundtruth.vision import OllamaVisionClient, extract_table
from groundtruth.vocab_sample import stratify

OUT = Path("data/results/vision_trial_corpus.json")
SEED = 77
NUMBER = re.compile(r"\d[\d,]*\.?\d*")


#: Letters 1960s scanners leave where digits were. Same table as disputes.py,
#: for the same reason: refusing a correct reading because the scan is damaged
#: measures the scanner, not the model.
_OCR_DIGITS = str.maketrans({
    "I": "1", "l": "1", "|": "1", "i": "1", "O": "0", "o": "0", "Q": "0",
    "S": "5", "s": "5", "Z": "2", "B": "8", "G": "6", "T": "7",
})


def _digit_stream(text: str) -> str:
    """Every digit on the page, in order, with all separators removed.

    Tokenising numbers was the first attempt and it was wrong, in the way this
    project keeps being wrong: the control failed rather than the thing under
    test. Statistics Canada writes thousands with a space -- "69 689" -- so a
    regex over number-shaped tokens produced "69" and "689" and never matched
    69689, and the first page of the trial scored 0% while the model was
    reading it flawlessly. A run of digits is separator-agnostic and
    format-agnostic, and it is what "is this number on the page" actually means.
    """
    return "".join(c for c in text.translate(_OCR_DIGITS) if c.isdigit())


def _values_in_ocr(records: list[dict], page_text: str) -> tuple[int, int]:
    """How many returned values can be found in the page's own text layer.

    High is strong evidence of reading. Low is NOT proof of invention: the OCR
    on these pages is often destroyed, which is the whole reason for the vision
    path. Reported per page so the two cases can be told apart by looking.
    """
    stream = _digit_stream(page_text)
    hits = total = 0
    for record in records:
        value = record.get("value")
        if value is None:
            continue
        total += 1
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        forms = {repr(number), f"{number:f}", str(value)}
        if number.is_integer():
            forms.add(str(int(number)))
        if any((d := "".join(c for c in f if c.isdigit()).lstrip("0")) and d in stream
               for f in forms):
            hits += 1
    return hits, total


def rescore() -> None:
    """Recompute the control over already-saved records.

    The model's answers are on disk, so a broken control can be repaired without
    paying for the pages again -- which is the only reason the first page's 0%
    was cheap to find out about.
    """
    archive = Archive()
    done = json.loads(OUT.read_text(encoding="utf-8"))
    for key, row in done.items():
        if "error" in row or not row.get("records"):
            continue
        page = {p.page: p for p in archive.pages(row["identifier"])}[row["page"]]
        hits, total = _values_in_ocr(row["records"], page.text)
        row["values_checked"], row["values_found_in_ocr"] = total, hits
    OUT.write_text(json.dumps(done, indent=2, ensure_ascii=False), encoding="utf-8")
    summarise(done)


def pick_pages(limit: int) -> list[tuple[str, str, int]]:
    """Table-routed pages spread across kinds of document, not one vein."""
    archive = Archive()
    strata = stratify(archive.load_index())
    rng = random.Random(SEED)
    out: list[tuple[str, str, int]] = []

    for stratum in sorted(strata, key=lambda k: -len(strata[k]))[:30]:
        if len(out) >= limit:
            break
        for item in rng.sample(strata[stratum], min(3, len(strata[stratum]))):
            if len(out) >= limit:
                break
            try:
                pages = archive.pages(item["identifier"])
            except Exception:  # noqa: BLE001
                continue
            tables = [p for p in pages if RPath.TABLE in route(p).paths]
            if not tables:
                continue
            # One page per document: the point is breadth across document
            # kinds, and a second page of the same table teaches nothing.
            page = rng.choice(tables)
            out.append((stratum, item["identifier"], page.page))
    return out


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    model = sys.argv[2] if len(sys.argv) > 2 else "qwen3.6:latest"

    archive = Archive()
    client = OllamaVisionClient(model=model, timeout=5400.0, think=False)

    done: dict = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    targets = pick_pages(limit)
    print(f"{len(targets)} table pages selected; {len(done)} already done", flush=True)

    for n, (stratum, ident, page_no) in enumerate(targets, 1):
        key = f"{ident}#{page_no}"
        if key in done:
            continue
        try:
            page = {p.page: p for p in archive.pages(ident)}[page_no]
            image = archive.page_image(ident, page_no)
        except Exception as exc:  # noqa: BLE001
            print(f"[{n}/{len(targets)}] {key}: fetch failed {exc}", flush=True)
            continue

        t0 = time.time()
        try:
            result = extract_table(page, image, client=client, year="")
        except Exception as exc:  # noqa: BLE001
            print(f"[{n}/{len(targets)}] {key}: FAILED {type(exc).__name__}", flush=True)
            done[key] = {"stratum": stratum, "error": str(exc)[:200],
                         "seconds": round(time.time() - t0, 1)}
            OUT.write_text(json.dumps(done, indent=2, ensure_ascii=False), encoding="utf-8")
            continue

        took = time.time() - t0
        records = [r.to_dict() for r in result.records]
        hits, total = _values_in_ocr(records, page.text)
        done[key] = {
            "stratum": stratum,
            "identifier": ident,
            "page": page_no,
            "seconds": round(took, 1),
            "n_records": len(records),
            "n_rejected": len(result.rejected),
            "values_checked": total,
            "values_found_in_ocr": hits,
            "ocr_chars": len(page.text),
            "records": records[:40],
            # The candidates the verifier threw out, not just how many. Keeping
            # only a count meant a later fix to the rules could not be replayed
            # over what the model had already returned -- and the rules did turn
            # out to be wrong, rejecting whole pages of correct values because a
            # column heading was not contiguous in the OCR. Paying for a page
            # twice to re-test a check is avoidable, so this avoids it.
            "rejected": result.rejected[:40],
        }
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(done, indent=2, ensure_ascii=False), encoding="utf-8")

        rate = f"{100*hits/total:.0f}%" if total else "n/a"
        print(f"[{n}/{len(targets)}] {key:44s} {len(records):3d} recs  "
              f"{took/60:5.1f} min  values-in-OCR {rate:>4s}  "
              f"rejected {len(result.rejected)}  [{stratum}]", flush=True)

    summarise(done)


def summarise(done: dict) -> None:
    ok = [d for d in done.values() if "error" not in d]
    if not ok:
        print("nothing completed")
        return
    recs = sorted(d["n_records"] for d in ok)
    secs = sorted(d["seconds"] for d in ok)
    checked = sum(d["values_checked"] for d in ok)
    found = sum(d["values_found_in_ocr"] for d in ok)
    rejected = sum(d["n_rejected"] for d in ok)

    def med(xs): return xs[len(xs) // 2]

    print(f"\n=== {len(ok)} table pages, {len(done)-len(ok)} failed ===")
    print(f"  records/page   median {med(recs)}  mean {sum(recs)/len(recs):.1f}  "
          f"range {recs[0]}-{recs[-1]}")
    print(f"  minutes/page   median {med(secs)/60:.1f}  first {secs[-1]/60:.1f} "
          f"(cold start inflates the max)")
    print(f"  values found in the page's own OCR: {found}/{checked} "
          f"({100*found/max(1,checked):.0f}%)")
    print(f"  records rejected for a label not on the page: {rejected}")
    print(f"  pages yielding nothing: {sum(1 for r in recs if r == 0)}/{len(ok)}")


if __name__ == "__main__":
    main()
