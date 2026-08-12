"""What would it cost to read the whole collection?

Not a slice. All 104,241 documents.

Every input here is measured on this project rather than assumed, and the ones
that are estimates say so. The point is to answer "is reading the whole archive
affordable" with a number somebody could check, instead of with a feeling.

    python scripts/cost_model.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# ---- measured on this corpus ----------------------------------------------

CORPUS_PAGES = 22_100_000          # stated by the collection
WORTH_READING = 0.531              # census: 120 items, 23,729 pages
PAGE_CHARS = 899                   # median OCR chars/page, measured

# Tokens. ~4 chars/token for English prose is the usual rule of thumb; the
# system prompt is fixed per page and measured directly from extract.py.
CHARS_PER_TOKEN = 4
SYSTEM_TOKENS = 700
OUTPUT_TOKENS_PER_PAGE = 260       # ~20 records at ~70 tokens, measured on dense pages

# ---- hardware, measured here ----------------------------------------------

LOCAL_TOK_PER_SEC = 7.9            # gemma4:12b on this machine, measured

# ---- rented hardware, ESTIMATED -------------------------------------------
#
# These are the only numbers here not measured on this project, and the answer
# is sensitive to them. A 12B model under vLLM with continuous batching does
# far better than the 7.9 tok/s of a single-stream local run, because the GPU is
# kept busy instead of idling between requests. 1,500-3,000 tok/s aggregate on
# an A100 is the range usually reported; the midpoint is used and the range is
# printed, because pretending to a single figure would be false precision.
RENTED = [
    ("A100 40GB, spot",   1.20, 1500, 3000),
    ("A100 80GB, on-dem", 1.80, 2000, 4000),
    ("H100, on-demand",   2.80, 4000, 8000),
]

# ---- hosted APIs, published list prices -----------------------------------
HOSTED = [
    ("small hosted model", 1.00, 5.00),
    ("mid hosted model",   3.00, 15.00),
]
BATCH_DISCOUNT = 0.5


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/results/cost_model.json")
    args = ap.parse_args()

    pages = int(CORPUS_PAGES * WORTH_READING)
    in_tok = pages * (PAGE_CHARS / CHARS_PER_TOKEN + SYSTEM_TOKENS)
    out_tok = pages * OUTPUT_TOKENS_PER_PAGE
    total_tok = in_tok + out_tok

    print(f"Reading all {CORPUS_PAGES/1e6:.1f}M pages of the collection\n")
    print(f"  pages worth reading   {pages:,}  ({WORTH_READING:.1%}, measured)")
    print(f"  input tokens          {in_tok/1e9:.2f}B")
    print(f"  output tokens         {out_tok/1e9:.2f}B")
    print(f"  total                 {total_tok/1e9:.2f}B\n")

    local_years = total_tok / LOCAL_TOK_PER_SEC / 86400 / 365
    print(f"On this machine at {LOCAL_TOK_PER_SEC} tok/s: {local_years:.0f} machine-years. "
          "Not a plan.\n")

    print("Renting a GPU (throughput ESTIMATED, see module):")
    rows = []
    for name, usd_hr, lo, hi in RENTED:
        hrs_lo, hrs_hi = total_tok / hi / 3600, total_tok / lo / 3600
        rows.append({
            "option": name, "usd_per_hour": usd_hr,
            "days": [round(hrs_lo / 24, 1), round(hrs_hi / 24, 1)],
            "usd": [round(hrs_lo * usd_hr), round(hrs_hi * usd_hr)],
        })
        print(f"  {name:<20} ${usd_hr:>5.2f}/hr   "
              f"{hrs_lo/24:>5.1f}-{hrs_hi/24:<5.1f} days   "
              f"${hrs_lo*usd_hr:>6,.0f}-${hrs_hi*usd_hr:,.0f}")

    print("\nHosted API at list price:")
    hosted = []
    for name, in_price, out_price in HOSTED:
        usd = in_tok / 1e6 * in_price + out_tok / 1e6 * out_price
        hosted.append({"option": name, "usd": round(usd),
                       "usd_batch": round(usd * BATCH_DISCOUNT)})
        print(f"  {name:<20} ${usd:>9,.0f}   (${usd*BATCH_DISCOUNT:,.0f} batched)")

    cheapest = min(r["usd"][0] for r in rows)
    print(f"\nCheapest credible path: roughly ${cheapest:,} of rented GPU time.")
    print("That fits inside a $5,000 fellowship with room for the mistakes, and it")
    print("is a ONE-TIME cost: afterwards the dataset costs everybody else nothing.")
    print("\nThe honest caveats:")
    print("  - throughput on rented hardware is estimated, not measured here;")
    print("    the first thing a funded run should do is measure it on 1,000 pages")
    print("    and re-derive this number before committing to the rest")
    print("  - it assumes the prose path only. Tables and figures are 26% of")
    print("    pages and need a vision model, which is slower and dearer per page")
    print("  - a re-run after any prompt change costs the same again, so the")
    print("    extraction prompt has to be settled BEFORE the money is spent")

    Path(args.out).write_text(json.dumps({
        "pages_worth_reading": pages,
        "tokens": {"input": int(in_tok), "output": int(out_tok), "total": int(total_tok)},
        "local_machine_years": round(local_years, 1),
        "rented": rows,
        "hosted": hosted,
        "caveats": [
            "rented throughput is estimated, not measured on this project",
            "prose path only; tables and figures are 26% of pages and cost more",
            "any prompt change means paying again, so settle the prompt first",
        ],
    }, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
