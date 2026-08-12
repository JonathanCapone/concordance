"""What would it cost to read the whole collection?

Not a slice. All 104,241 documents.

Every input here is measured on this project rather than assumed, and the ones
that are estimates say so in the output as well as in the source. The point is
to answer "is reading the whole archive affordable" with a number somebody could
check, instead of with a feeling.

Two paths are costed separately, because they behave nothing alike. The prose
path is cheap, fast and yields a few measurements per page. The vision path is
slow, dearer, and yields several times as many -- so a model that costs only the
prose path answers a different and easier question than the one being asked.

    python scripts/cost_model.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# ---- measured on this corpus ----------------------------------------------

CORPUS_PAGES = 22_100_000          # stated by the collection

#: Revised upward after a routing bug was fixed. A line counted as prose only if
#: it held eight words, which is a fact about typography rather than content and
#: was discarding about 6.3 million pages -- worst of all in the legislative
#: record, because that is how minutes have always been typeset. Measured over
#: 8,372 pages from 34 documents in 26 collections. The old figure was 0.531.
WORTH_READING = 0.695

#: Of the pages worth reading, how many carry text an ordinary model can read.
#: The rest need the scan itself. Same sample.
TEXT_SHARE = 0.730
VISION_SHARE = 0.270

PAGE_CHARS = 899                   # median OCR chars/page, measured

#: Measurements recovered per page, by path. The prose figure is from 83 timed
#: pages; the vision figure is the median over 24 table pages read by qwen3.6
#: across 11 collections -- census tables, sessional papers of two parliaments,
#: municipal reports, a liquor board, a mining microlog, an attorney general's
#: returns. 535 measurements, 3 pages yielding nothing, range 0-33.
#:
#: The median is used rather than the mean (22.3) so that neither the empty
#: pages nor the densest one decides the corpus estimate. The empty pages are
#: real and are counted: a table page that gives nothing is part of the rate.
#:
#: The gap between the two figures is the reason pages are the wrong unit for
#: judging this split. Tables are 27% of the pages and most of the actual data.
RECORDS_PER_PROSE_PAGE = 4.2
RECORDS_PER_TABLE_PAGE = 25

# Tokens. ~4 chars/token for English prose is the usual rule of thumb; the
# system prompt is fixed per page and measured directly from extract.py.
CHARS_PER_TOKEN = 4
SYSTEM_TOKENS = 900                # grew when the prompt stopped being water-only
OUTPUT_TOKENS_PER_PAGE = 260       # ~20 records at ~70 tokens, measured on dense pages

#: A page image costs far more to read than its text. Roughly 1,600 tokens for a
#: 1500px scan at this model's patch size, plus a longer answer because a table
#: page yields four times the records.
VISION_INPUT_TOKENS = 1_600
VISION_OUTPUT_TOKENS = 900

# ---- hardware, measured here ----------------------------------------------

LOCAL_TOK_PER_SEC = 7.9            # gemma4:12b on this machine, measured

#: qwen3.6 on an RTX 2080, measured over 24 pages: median 8.0 minutes each,
#: with only 18% of a 29.6 GB model resident in 8 GB of VRAM. That figure says
#: more about the card than the model and is here to be honest about what a
#: contributor's machine can do, not to be extrapolated.
LOCAL_VISION_MIN_PER_PAGE = 8.0

# ---- rented hardware, ESTIMATED -------------------------------------------
#
# These are the only numbers here not measured on this project, and the answer
# is sensitive to them. A 12B model under vLLM with continuous batching does far
# better than the 7.9 tok/s of a single-stream local run, because the GPU is
# kept busy instead of idling between requests. 1,500-3,000 tok/s aggregate on
# an A100 is the range usually reported; the range is printed rather than a
# midpoint, because pretending to a single figure would be false precision.
#
# The vision model is a 36B mixture of experts that fires 8 of 256 per token, so
# its active parameter count is far below its size -- which is why it is worth
# renting rather than buying. Assumed to run at half the dense model's aggregate
# throughput once resident, which is a guess and is labelled as one.
RENTED = [
    ("A100 40GB, spot",   1.20, 1500, 3000),
    ("A100 80GB, on-dem", 1.80, 2000, 4000),
    ("H100, on-demand",   2.80, 4000, 8000),
]
VISION_THROUGHPUT_PENALTY = 0.5

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
    text_pages = int(pages * TEXT_SHARE)
    table_pages = pages - text_pages

    text_in = text_pages * (PAGE_CHARS / CHARS_PER_TOKEN + SYSTEM_TOKENS)
    text_out = text_pages * OUTPUT_TOKENS_PER_PAGE
    vis_in = table_pages * (VISION_INPUT_TOKENS + SYSTEM_TOKENS)
    vis_out = table_pages * VISION_OUTPUT_TOKENS
    total_tok = text_in + text_out + vis_in + vis_out

    records = text_pages * RECORDS_PER_PROSE_PAGE + table_pages * RECORDS_PER_TABLE_PAGE

    print(f"Reading all {CORPUS_PAGES/1e6:.1f}M pages of the collection\n")
    print(f"  pages worth reading   {pages:,}  ({WORTH_READING:.1%}, measured)")
    print(f"    text path           {text_pages:,}  ({TEXT_SHARE:.0%})")
    print(f"    vision path         {table_pages:,}  ({VISION_SHARE:.0%})")
    print(f"  tokens                {total_tok/1e9:.2f}B "
          f"({(text_in+text_out)/1e9:.2f}B text, {(vis_in+vis_out)/1e9:.2f}B vision)")
    print(f"  measurements expected {records/1e6:.0f}M "
          f"({table_pages*RECORDS_PER_TABLE_PAGE/records:.0%} of them from tables, "
          f"which are {VISION_SHARE:.0%} of the pages)\n")

    local_years = (text_in + text_out) / LOCAL_TOK_PER_SEC / 86400 / 365
    vision_years = table_pages * LOCAL_VISION_MIN_PER_PAGE / 60 / 24 / 365
    print(f"On this machine: {local_years:.0f} machine-years of prose, plus "
          f"{vision_years:,.0f} of tables. Not a plan.\n")

    print("Renting a GPU (throughput ESTIMATED, see module):")
    rows = []
    for name, usd_hr, lo, hi in RENTED:
        text_hr_lo, text_hr_hi = (text_in + text_out) / hi / 3600, (text_in + text_out) / lo / 3600
        vlo, vhi = lo * VISION_THROUGHPUT_PENALTY, hi * VISION_THROUGHPUT_PENALTY
        vis_hr_lo, vis_hr_hi = (vis_in + vis_out) / vhi / 3600, (vis_in + vis_out) / vlo / 3600
        hrs_lo, hrs_hi = text_hr_lo + vis_hr_lo, text_hr_hi + vis_hr_hi
        rows.append({
            "option": name, "usd_per_hour": usd_hr,
            "days": [round(hrs_lo / 24, 1), round(hrs_hi / 24, 1)],
            "usd": [round(hrs_lo * usd_hr), round(hrs_hi * usd_hr)],
            "usd_text_only": [round(text_hr_lo * usd_hr), round(text_hr_hi * usd_hr)],
        })
        print(f"  {name:<20} ${usd_hr:>5.2f}/hr   "
              f"{hrs_lo/24:>5.1f}-{hrs_hi/24:<6.1f} days   "
              f"${hrs_lo*usd_hr:>6,.0f}-${hrs_hi*usd_hr:,.0f}"
              f"   (text alone: ${text_hr_lo*usd_hr:,.0f}-${text_hr_hi*usd_hr:,.0f})")

    print("\nHosted API at list price:")
    hosted = []
    for name, in_price, out_price in HOSTED:
        usd = (text_in + vis_in) / 1e6 * in_price + (text_out + vis_out) / 1e6 * out_price
        hosted.append({"option": name, "usd": round(usd),
                       "usd_batch": round(usd * BATCH_DISCOUNT)})
        print(f"  {name:<20} ${usd:>9,.0f}   (${usd*BATCH_DISCOUNT:,.0f} batched)")

    cheapest = min(r["usd"][0] for r in rows)
    cheapest_text = min(r["usd_text_only"][0] for r in rows)
    print(f"\nCheapest credible path: roughly ${cheapest:,} of rented GPU time for "
          f"both paths,")
    print(f"or ${cheapest_text:,} for the text alone, which leaves most of the "
          "measurements unread.")
    print("Either fits inside a $5,000 fellowship, and it is a ONE-TIME cost:")
    print("afterwards the dataset costs everybody else nothing.")
    print("\nThe honest caveats:")
    print("  - throughput on rented hardware is estimated, not measured here;")
    print("    the first thing a funded run should do is measure it on 1,000 pages")
    print("    and re-derive this number before committing to the rest")
    print("  - the vision throughput penalty is a guess, and vision is now most")
    print("    of the cost, so it is the single number most worth measuring first")
    print("  - a re-run after any prompt change costs the same again, so the")
    print("    extraction prompt has to be settled BEFORE the money is spent")

    Path(args.out).write_text(json.dumps({
        "pages_worth_reading": pages,
        "text_pages": text_pages,
        "table_pages": table_pages,
        "expected_measurements": int(records),
        "share_of_measurements_from_tables":
            round(table_pages * RECORDS_PER_TABLE_PAGE / records, 3),
        "tokens": {
            "text_input": int(text_in), "text_output": int(text_out),
            "vision_input": int(vis_in), "vision_output": int(vis_out),
            "total": int(total_tok),
        },
        "local_machine_years": {"prose": round(local_years, 1),
                                "vision": round(vision_years, 1)},
        "rented": rows,
        "hosted": hosted,
        "caveats": [
            "rented throughput is estimated, not measured on this project",
            "the vision throughput penalty is a guess and vision is most of the "
            "cost, so it is the first thing a funded run should measure",
            "table pages are 27% of the pages and about four times as dense in "
            "measurements, so costing the prose path alone answers an easier "
            "question than the one being asked",
            "any prompt change means paying again, so settle the prompt first",
        ],
    }, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
