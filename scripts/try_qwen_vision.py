"""Can qwen3.6 read a table that 2013-era OCR destroyed?

This is the decisive question for Path B. llava invents table structure -- it
returns plausible rows that are not on the page -- which makes it worse than
useless, because a fabricated table looks exactly like a recovered one. If a
vision model can read these scans, roughly a quarter of the corpus stops being
unreachable.

The page chosen is Brantford 1962, page 15: a monthly flow table whose OCR is
damaged but not destroyed, so the surviving numbers can be used to check the
model's answer against the scan without a human re-reading the whole page.

    TABLE I FLOW - MILX.IQN GALLOLS MONTH MAX. DAILY r low MIN. DAILY
    TOT ^i.r i' low AVa. DAILY r .LOW TOTAL MONTHLY -C £ow
    Jan. 6.976 4.609 5.700 176.547
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from groundtruth.archive import Archive
from groundtruth.vision import OllamaVisionClient, extract_table

IDENT, PAGE = "brantfordsewaget23777", 15

#: Read off the surviving OCR of the same page. If the model returns these, it
#: is reading the scan; if it returns a tidy table containing none of them, it
#: is inventing one -- which is exactly how llava failed.
KNOWN = {"6.976", "4.609", "5.700", "176.547", "6.200", "4.377", "5.425",
         "151.607", "7.903", "4.428", "5.675", "176.026"}


def main() -> None:
    models = sys.argv[1:] or ["qwen3.6:latest"]
    a = Archive()
    page = {p.page: p for p in a.pages(IDENT)}[PAGE]
    image = a.page_image(IDENT, PAGE)
    print(f"page image {len(image)/1e6:.2f} MB", flush=True)
    print(f"OCR: {' '.join(page.text.split())[:200]}\n", flush=True)

    for model in models:
        client = OllamaVisionClient(model=model, timeout=5400.0, think=False)
        t0 = time.time()
        try:
            result = extract_table(
                page, image, client=client,
                title="Brantford Sewage Treatment Plant Annual Report", year="1962")
        except Exception as exc:  # noqa: BLE001
            print(f"{model}: FAILED after {(time.time()-t0)/60:.1f} min -- "
                  f"{type(exc).__name__}: {exc}", flush=True)
            continue

        took = time.time() - t0
        records = [r.to_dict() for r in result.records]
        values = {str(r.get("value")) for r in records}
        hits = sorted(v for v in KNOWN if any(v in s for s in values))

        print(f"\n=== {model} -- {len(records)} records in {took/60:.1f} min ===", flush=True)
        print(f"  known values recovered: {len(hits)}/{len(KNOWN)}  {hits}", flush=True)
        for d in records[:20]:
            print(f"  {str(d.get('parameter'))[:26]:26s} {str(d.get('value')):>12s} "
                  f"{str(d.get('unit'))[:14]:14s} {str(d.get('period') or '')[:9]}", flush=True)
            print(f"      cell: {(d.get('provenance') or {}).get('source_text','')[:78]!r}",
                  flush=True)

        out = Path("data/results/vision_trial.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        payload[model] = {
            "identifier": IDENT, "page": PAGE, "seconds": round(took, 1),
            "n_records": len(records), "known_recovered": hits,
            "known_total": len(KNOWN), "records": records,
        }
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  -> {out}", flush=True)


if __name__ == "__main__":
    main()
