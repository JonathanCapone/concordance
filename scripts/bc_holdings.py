"""Count the collection's British Columbia holdings, checkably.

The application names these numbers, so they must recompute from the frozen
August 11 catalogue snapshot the same way every other claimed figure does.
BACKLOG B15's acceptance criterion: BC counts come from a script, not a grep
remembered from a conversation.

Usage: python scripts/bc_holdings.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SNAPSHOT = Path("data/cache/index_governmentpublications.json")

#: What counts as a BC item: the title or creator names the province or one of
#: its unambiguous regions. Deliberately conservative -- "Victoria" alone is
#: NOT here, because most Victoria hits in this collection are Victoria
#: County, Ontario (Lindsay, Omemee, Fenelon Falls), and an inflated BC count
#: in a BC fellowship application would be the worst possible place to be
#: sloppy.
BC = re.compile(
    r"british columbia|\bb\.\s?c\.\b|vancouver|okanagan|fraser (river|valley)"
    r"|kootenay|vancouver island|lower mainland",
    re.I,
)

WATER = re.compile(r"water (management|rights|resources|investigations)", re.I)

FIRST_NATIONS_SERIES = re.compile(
    r"water rights in British Columbia.*rights of the (.+?)"
    r"(?: Band| First Nation|$)",
    re.I,
)


def main() -> int:
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    items = snap if isinstance(snap, list) else snap.get("items") or []

    bc = [it for it in items
          if BC.search(f"{it.get('title') or ''} {it.get('creator') or ''}")]
    water = [it for it in bc if WATER.search(str(it.get("title") or ""))]
    communities = set()
    for it in items:
        got = FIRST_NATIONS_SERIES.search(str(it.get("title") or ""))
        if got:
            communities.add(got.group(1).strip(" .:"))

    print(f"catalogue items:                     {len(items):>7,}")
    print(f"BC items (title/creator, conservative): {len(bc):>4,}")
    print(f"  of which water-focused:            {len(water):>7,}")
    print(f"First Nations water-rights series:   {len(communities):>7,} communities")
    for name in sorted(communities):
        print(f"    - {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
