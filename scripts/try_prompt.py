"""Does the widened prompt read the pages the router now reaches?

Three pages of "Hamilton: An Adventure in Good Living" (1983) that the old
router discarded for being set in narrow columns. With the router fixed they
reach the extractor, and the extractor -- whose every example was BOD and mg/L
-- returned nothing at all from text that plainly says "75 elementary schools".

The gold set still governs accuracy on water reports. This only asks whether the
non-water half of the archive is visible at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from concordance.archive import Archive
from concordance.extract import OllamaClient, extract_prose
from concordance.router import Path as RPath, route

IDENT = "hamiltonadventur00unse"
PAGES = (20, 16, 21, 28)


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "gemma4:12b"
    archive = Archive()
    pages = {p.page: p for p in archive.pages(IDENT)}
    client = OllamaClient(model=model)
    total = 0

    for page_no in PAGES:
        page = pages[page_no]
        if RPath.PROSE not in route(page).paths:
            print(f"p{page_no}: not routed to prose", flush=True)
            continue
        result = extract_prose(page, client=client,
                               title="Hamilton : An Adventure in Good Living",
                               year="1983")
        total += len(result.records)
        print(f"\n=== p{page_no}: {len(result.records)} records "
              f"({len(result.rejected)} rejected) ===", flush=True)
        for record in result.records:
            d = record.to_dict()
            print(f"  {str(d.get('parameter'))[:34]:34s} {str(d.get('value')):>10s} "
                  f"{str(d.get('unit'))[:14]:14s} [{d.get('kind')}]", flush=True)
            print(f"      {(d.get('provenance') or {}).get('source_text','')[:88]!r}",
                  flush=True)

    print(f"\nTOTAL {total} records from {len(PAGES)} pages (was 0)", flush=True)


if __name__ == "__main__":
    main()
