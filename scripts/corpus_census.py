"""How much of the collection is actually worth reading?

"Read the whole archive" is a claim, and this is the measurement behind it. A
random sample of items is routed page by page and the result extrapolated to all
104,241, with an interval rather than a point estimate -- because a sample of a
few hundred out of a hundred thousand deserves error bars, and quoting a single
confident number from it would be exactly the kind of overreach this project
keeps catching itself in.

Costs one OCR download per sampled item and no model calls at all: routing is
deliberately cheap so it can run over the whole corpus.

    python scripts/corpus_census.py --sample 300
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from groundtruth.archive import Archive              # noqa: E402
from groundtruth.router import Path as RPath, route  # noqa: E402


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a proportion.

    Used rather than the normal approximation because it behaves properly for
    small samples and proportions near 0 or 1, which is where a corpus census
    like this actually lives.
    """
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=300)
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--out", default="data/results/corpus_census.json")
    ap.add_argument("--sleep", type=float, default=0.4,
                    help="pause between items; archive.org is a charity")
    args = ap.parse_args()

    archive = Archive()
    index = archive.load_index()
    rng = random.Random(args.seed)
    sample = rng.sample(index, min(args.sample, len(index)))

    path_pages: collections.Counter = collections.Counter()
    items_with_measurements = 0
    total_pages = 0
    worth_pages = 0
    per_item_pages: list[int] = []
    per_item_worth: list[int] = []
    failures = 0

    t0 = time.time()
    for i, item in enumerate(sample, 1):
        ident = item["identifier"]
        try:
            pages = archive.pages(ident)
        except Exception:  # noqa: BLE001
            failures += 1
            continue
        if not pages:
            failures += 1
            continue

        routes = [route(p) for p in pages]
        worth = [r for r in routes if r.worth_reading]
        measured = [r for r in routes if RPath.PROSE in r.paths or RPath.TABLE in r.paths]

        total_pages += len(pages)
        worth_pages += len(worth)
        per_item_pages.append(len(pages))
        per_item_worth.append(len(worth))
        if measured:
            items_with_measurements += 1
        for r in routes:
            for p in r.paths:
                path_pages[p.value] += 1

        if i % 25 == 0:
            print(f"  {i}/{len(sample)}  {time.time()-t0:.0f}s  "
                  f"{total_pages:,} pages seen", flush=True)
        time.sleep(args.sleep)

    n = len(per_item_pages)
    if n == 0:
        print("no items could be read")
        return 1

    lo, hi = wilson(items_with_measurements, n)
    worth_frac = worth_pages / total_pages if total_pages else 0
    wlo, whi = wilson(worth_pages, total_pages)
    mean_pages = total_pages / n

    CORPUS_ITEMS = 104_241
    CORPUS_PAGES = 22_100_000

    print(f"\nsampled {n} items ({failures} unreadable), {total_pages:,} pages\n")
    print(f"items carrying measurements : {items_with_measurements}/{n} "
          f"= {items_with_measurements/n:.1%}  (95% CI {lo:.1%}-{hi:.1%})")
    print(f"pages worth reading         : {worth_pages:,}/{total_pages:,} "
          f"= {worth_frac:.1%}  (95% CI {wlo:.1%}-{whi:.1%})")
    print(f"mean pages per item         : {mean_pages:.0f}")
    print("\nrouting, per page:")
    for path, count in path_pages.most_common():
        print(f"  {path:<10} {count:>7,}  {count/total_pages:>6.1%}")

    print(f"\nextrapolated to the full collection ({CORPUS_ITEMS:,} items, "
          f"{CORPUS_PAGES/1e6:.1f}M pages):")
    print(f"  items with measurements : {int(lo*CORPUS_ITEMS):,} - {int(hi*CORPUS_ITEMS):,}")
    print(f"  pages worth reading     : {int(wlo*CORPUS_PAGES):,} - {int(whi*CORPUS_PAGES):,}")

    # What that costs, at the throughput actually observed on this machine.
    SECONDS_PER_PAGE = 150
    mid_pages = int(worth_frac * CORPUS_PAGES)
    print(f"\nat the ~{SECONDS_PER_PAGE}s/page measured locally, reading every one of "
          f"those ~{mid_pages/1e6:.1f}M pages is ~{mid_pages*SECONDS_PER_PAGE/86400/365:.0f} "
          "machine-years on one consumer GPU.")
    print("  So a corpus-wide pass is not a local job. It is a funded batch run, once,")
    print("  after which the dataset costs nobody anything to use.")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "sampled_items": n,
        "unreadable": failures,
        "pages_seen": total_pages,
        "items_with_measurements": items_with_measurements,
        "item_rate": items_with_measurements / n,
        "item_rate_ci95": [lo, hi],
        "page_worth_rate": worth_frac,
        "page_worth_rate_ci95": [wlo, whi],
        "mean_pages_per_item": mean_pages,
        "paths_per_page": dict(path_pages),
        "extrapolation": {
            "corpus_items": CORPUS_ITEMS,
            "corpus_pages": CORPUS_PAGES,
            "items_with_measurements_range": [int(lo * CORPUS_ITEMS), int(hi * CORPUS_ITEMS)],
            "pages_worth_reading_range": [int(wlo * CORPUS_PAGES), int(whi * CORPUS_PAGES)],
        },
        "caveat": (
            "Extrapolated from a random sample. The interval is Wilson score at 95%, "
            "and reflects sampling error only -- it does not capture the collection's "
            "unevenness across agencies and decades, which is real and larger."
        ),
    }, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
