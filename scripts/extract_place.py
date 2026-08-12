"""Read every surviving report for one place, and write out the series.

This is the first thing in the project that produces a *result* rather than a
capability: eleven annual reports for one town become a measured time series with
provenance on every point.

Resumable and incremental by design. Extraction runs at roughly 200 seconds per
page on a local model, so a full town is an hour or more; the run must survive
being interrupted, and each page is written to disk the moment it completes.

    python scripts/extract_place.py --place "Owen Sound" --title-filter "owen sound"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from groundtruth.archive import Archive                        # noqa: E402
from groundtruth.extract import OllamaClient, extract_prose    # noqa: E402
from groundtruth.parameters import facility_of                 # noqa: E402
from groundtruth.router import Path as RPath, route            # noqa: E402


def load_done(out_path: Path) -> tuple[list[dict], set[str]]:
    """Records already extracted, and which (item, page) pairs they cover."""
    if not out_path.exists():
        return [], set()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    done = {f"{p.get('identifier')}#{p.get('page')}"
            for r in records if (p := r.get("provenance"))}
    # Pages that yielded nothing still count as done, or every resume would
    # re-read the barren pages first and never reach new material.
    done |= set(payload.get("pages_attempted", []))
    return records, done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", required=True, help='e.g. "Owen Sound"')
    ap.add_argument("--title-filter", required=True, help="substring match on item title")
    ap.add_argument("--model", default="gemma4:12b")
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-items", type=int, default=0, help="0 = no limit")
    ap.add_argument("--timeout", type=float, default=900.0)
    args = ap.parse_args()

    archive = Archive()
    client = OllamaClient(model=args.model, timeout=args.timeout)
    slug = args.place.lower().replace(" ", "-")
    out_path = Path(args.out or f"data/results/{slug}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    records, done = load_done(out_path)
    attempted: list[str] = sorted(done)
    print(f"{args.place}: resuming with {len(records)} records, {len(done)} pages already done",
          flush=True)

    items = sorted(
        archive.iter_items(title_contains=args.title_filter),
        key=lambda it: str(it.get("year") or "9999"),
    )
    # Annual reports only. Later one-off studies about the same place are a
    # different kind of document and would pollute a plant's operating series.
    items = [it for it in items if "annual report" in str(it.get("title", "")).lower()
             or "sewage treatment plant" in str(it.get("title", "")).lower()]
    if args.max_items:
        items = items[: args.max_items]
    print(f"{len(items)} annual reports to read\n", flush=True)

    def flush() -> None:
        out_path.write_text(
            json.dumps(
                {
                    "place": args.place,
                    "model": client.name,
                    "n_records": len(records),
                    "pages_attempted": attempted,
                    "records": records,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    for it in items:
        ident = it["identifier"]
        year = str(it.get("year") or "")
        title = str(it.get("title") or "")
        pubs = it.get("publisher") or []
        pub = (pubs[0] if isinstance(pubs, list) and pubs else pubs) or ""

        try:
            pages = archive.pages(ident)
        except Exception as exc:  # noqa: BLE001
            print(f"  {ident} {year}: FAILED to load pages ({exc})", flush=True)
            continue

        worth = [p for p in pages if RPath.PROSE in route(p).paths]
        facility = facility_of(title)
        print(f"  {ident} {year}: {len(pages)} pages, {len(worth)} prose"
              f"  [{facility or 'unclassified facility'}]", flush=True)

        for page in worth:
            key = f"{ident}#{page.page}"
            if key in done:
                continue
            t0 = time.time()
            try:
                result = extract_prose(
                    page, client=client, title=title, publisher=str(pub), year=year
                )
            except Exception as exc:  # noqa: BLE001
                # A timeout here is a throughput problem, not a bad page -- and it
                # selects against exactly the pages worth having. The 1972 Owen
                # Sound report timed out on its page 11, which is 1,920 characters
                # of clean OCR carrying 35 numbers and 14 units: the densest
                # measurement page in the document. Retry once with a longer
                # budget rather than losing the best page in the report.
                if "timed out" not in str(exc).lower():
                    print(f"    p{page.page}: ERROR {str(exc)[:70]}", flush=True)
                    continue
                print(f"    p{page.page}: timed out after {time.time()-t0:.0f}s, "
                      "retrying with a longer budget", flush=True)
                patient = OllamaClient(model=client.model, timeout=client.timeout * 3)
                try:
                    result = extract_prose(
                        page, client=patient, title=title, publisher=str(pub), year=year
                    )
                except Exception as exc2:  # noqa: BLE001
                    print(f"    p{page.page}: FAILED on retry: {str(exc2)[:60]}", flush=True)
                    continue

            for r in result.records:
                d = r.to_dict()
                # The report is *for* a year; the model rarely repeats it in
                # every sentence, so stamp it from the item where it is missing.
                #
                # It also returns bare month names -- "March", "December 9" --
                # when a sentence names a month without repeating the year. Those
                # parse as no year at all and drop out of every series in silence,
                # which is the worst way to lose data. Anchor them to the report's
                # own year instead.
                period = str(d.get("period") or "")
                if year and not re.search(r"\b(1[89]\d{2}|20\d{2})\b", period):
                    d["period"] = f"{year} {period}".strip() if period else year
                if not d.get("place"):
                    d["place"] = args.place
                # One town commonly has several facilities measuring opposite
                # things. Without this, a 1992 drinking-water reading and a 1969
                # effluent reading share a place name and end up on one chart.
                # The sentence wins over the title: one document routinely
                # covers several facilities, and the title names none of them.
                if not d.get("facility"):
                    d["facility"] = facility
                records.append(d)

            done.add(key)
            attempted.append(key)
            flush()
            print(
                f"    p{page.page}: {time.time()-t0:>5.0f}s  +{len(result.records)} records "
                f"(total {len(records)})",
                flush=True,
            )

    flush()
    print(f"\nwrote {out_path}  —  {len(records)} records from {len(items)} reports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
