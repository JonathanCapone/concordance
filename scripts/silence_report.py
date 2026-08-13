"""Map what stopped being measured, and check it isn't a digitisation artefact.

The negative record is the finding this project is most interested in, and also
the one easiest to get wrong. A town that vanishes from a collection may have
stopped reporting -- or may simply never have been scanned. Those are completely
different claims and the data looks identical.

So every silence claim here is paired with a control: if a series goes quiet in
year Y, does the *rest of the collection* also go quiet in year Y? If the archive
keeps growing while one series dies, the silence is real. If everything stops at
once, it is a scanning boundary and means nothing about the world.

    python scripts/silence_report.py
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from concordance.archive import Archive     # noqa: E402
from concordance.science import silence     # noqa: E402

#: Real title shapes in the corpus. A single pattern gets this badly wrong in
#: both directions: too strict and it finds 41 municipalities, too loose and it
#: invents 411 by treating "1963 operating summary" as a place.
PATTERNS = [
    re.compile(r"^(?P<p>.+?)\s*:\s*water pollution control plant", re.I),
    re.compile(r"\bon (?:the )?(?:city|town|village|township) of (?P<p>.+?)\s+water pollution", re.I),
    re.compile(r"\bon (?P<p>.+?)\s+water pollution control plant", re.I),
    re.compile(r"^(?P<p>.+?)\s+water pollution control plant", re.I),
]

NOISE = re.compile(
    r"^(annual report|report|operating summary|\d{4} operating summary|"
    r"report on the public hearing|operating cost|thirty|evaluation|expansion|"
    r"ontario water resources)", re.I)


def place_of(title: str) -> str | None:
    t = re.sub(r"\s+", " ", title).strip()
    for pat in PATTERNS:
        m = pat.search(t)
        if not m:
            continue
        p = m.group("p").strip(" ,.[]")
        p = re.sub(r"^(the )?(corporation of )?(the )?", "", p, flags=re.I)
        p = re.sub(r"^(city|town|village|township) of ", "", p, flags=re.I)
        p = re.sub(r"\b(annual report|report)\b.*$", "", p, flags=re.I).strip(" ,.")
        p = re.sub(r"^\d{4},?\s*", "", p).strip(" ,.")
        if not p or len(p) < 3 or len(p) > 42 or NOISE.match(p):
            continue
        return p.title()
    return None


def year_of(item) -> int | None:
    try:
        return int(str(item.get("year"))[:4])
    except (TypeError, ValueError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/results/silence_report.json")
    args = ap.parse_args()

    archive = Archive()
    index = archive.load_index()

    coverage: dict[str, set[int]] = collections.defaultdict(set)
    for item in archive.iter_items(title_contains="water pollution control plant"):
        place = place_of(str(item.get("title", "")))
        year = year_of(item)
        if place and year:
            coverage[place].add(year)

    # The horizon must NOT be derived from the same municipalities being tested.
    # Doing that is circular: if every parsed town's last report is 1974 then the
    # horizon is 1974, and no town can ever register as having gone silent --
    # the measurement defines away the thing it is measuring.
    #
    # Take it instead from every item in the series, including those whose place
    # name did not parse. Those stragglers (1978, 1988) prove the collection was
    # still capable of holding a report of this kind long after 1974, which is
    # exactly what makes the 1974 stop meaningful.
    horizon = max(
        y
        for it in archive.iter_items(title_contains="water pollution control plant")
        if (y := year_of(it)) is not None
    )
    reports = [silence(p, ys, horizon=horizon) for p, ys in coverage.items()]
    reports.sort(key=lambda r: (-len(r.reported_years), r.place))

    # Where does the series die?
    cliff = collections.Counter(r.silent_since for r in reports if r.silent_since)
    worst_year, worst_n = cliff.most_common(1)[0] if cliff else (None, 0)

    # -- THE CONTROL -------------------------------------------------------
    # Did the collection as a whole also stop in that year?
    def era_split(items, label):
        pre = post = 0
        for it in items:
            y = year_of(it)
            if y is None:
                continue
            if y < worst_year:
                pre += 1
            else:
                post += 1
        return {"series": label, "before": pre, "from_cliff_onward": post}

    controls = [
        era_split(
            list(archive.iter_items(publisher_contains="Ontario Ministry of the Environment")),
            "Ontario Ministry of the Environment (all publications)",
        ),
        era_split(
            [it for it in index if "ontario" in str(it.get("title", "")).lower()],
            "any title mentioning Ontario",
        ),
        era_split(
            list(archive.iter_items(title_contains="water pollution control plant")),
            "water pollution control plant reports (the series under test)",
        ),
    ]

    print(f"municipalities with dated reports : {len(reports)}")
    print(f"corpus horizon                    : {horizon}")
    print(f"\nlargest simultaneous stop: {worst_n} municipalities go silent from {worst_year}\n")

    print("--- control: did the collection itself stop? ---")
    for c in controls:
        verdict = "CONTINUES" if c["from_cliff_onward"] > c["before"] * 0.5 else "also stops"
        print(f"  {c['series'][:52]:<54} before {c['before']:>5} | after {c['from_cliff_onward']:>5}  {verdict}")

    survives = all(
        c["from_cliff_onward"] > c["before"] * 0.5
        for c in controls
        if "under test" not in c["series"]
    )
    print(
        "\nverdict: "
        + (
            "the archive keeps growing while this series dies -- the silence is REAL"
            if survives
            else "the whole collection thins at the same time -- likely a DIGITISATION BOUNDARY"
        )
    )

    print("\n--- longest-running municipalities ---")
    for r in reports[:12]:
        print("  " + r.describe())

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "n_municipalities": len(reports),
                "horizon": horizon,
                "largest_simultaneous_stop": {"year": worst_year, "municipalities": worst_n},
                "digitisation_control": controls,
                "control_verdict": "real" if survives else "possible digitisation boundary",
                "caveat": (
                    "A gap means not-digitised OR not-reported. The control above "
                    "distinguishes the two at collection level, but an individual "
                    "municipality's gap has not been checked against that town's own "
                    "holdings and should not be cited as institutional silence on its own."
                ),
                "municipalities": [
                    {
                        "place": r.place,
                        "first_year": r.first_year,
                        "last_year": r.last_year,
                        "reported_years": r.reported_years,
                        "missing_years": r.missing_years,
                        "silent_since": r.silent_since,
                        "continuity": round(r.continuity, 3),
                        "longest_gap": r.longest_gap,
                    }
                    for r in reports
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
