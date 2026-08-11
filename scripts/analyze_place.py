"""Turn one place's extracted records into findings.

Runs against whatever has been extracted so far, so it can be used while a long
extraction is still going.

    python scripts/analyze_place.py --file data/results/owen-sound.json
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from groundtruth.models import Provenance, Record          # noqa: E402
from groundtruth.science import (                          # noqa: E402
    changepoint,
    series_from_records,
    silence,
    trend,
)


def load_records(path: Path) -> tuple[list[Record], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: list[Record] = []
    for d in payload.get("records", []):
        p = d.get("provenance") or {}
        out.append(
            Record(
                kind=d["kind"],
                parameter=d.get("parameter", ""),
                value=d.get("value"),
                unit=d.get("unit"),
                qualifier=d.get("qualifier"),
                stream=d.get("stream", "unknown"),
                place=d.get("place"),
                period=d.get("period"),
                confidence=d.get("confidence", 0.0),
                provenance=Provenance(
                    identifier=p.get("identifier", ""),
                    page=p.get("page"),
                    source_text=p.get("source_text", ""),
                ),
            )
        )
    return out, payload.get("place", "?")


#: Parameters worth charting for a sewage treatment plant, with the stream that
#: makes them meaningful. Effluent BOD is what the town discharged; influent BOD
#: is what arrived. Removal percentage is how well the plant worked.
TARGETS = [
    ("BOD", "effluent", "what the town discharged"),
    ("BOD", "influent", "what arrived at the plant"),
    ("suspended solids", "effluent", "solids discharged"),
    ("suspended solids", "influent", "solids arriving"),
    ("BOD removal", None, "how well the plant worked"),
    ("suspended solids removal", None, "solids removal efficiency"),
    ("flow", None, "hydraulic load"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="data/results/owen-sound.json")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"no such file: {path}")
        return 1

    records, place = load_records(path)
    obs = [r for r in records if r.kind == "observation"]
    print(f"=== {place} ===")
    print(f"{len(records)} records  ({len(obs)} observations, "
          f"{sum(1 for r in records if r.kind=='design')} design, "
          f"{sum(1 for r in records if r.kind=='standard')} standard, "
          f"{sum(1 for r in records if r.kind=='conclusion')} conclusion)")

    years = sorted({int(str(r.period)[:4]) for r in records
                    if r.period and str(r.period)[:4].isdigit()})
    if years:
        s = silence(place, years, horizon=1996)
        print(f"coverage: {s.describe()}")
    print()

    print("--- series ---")
    any_series = False
    for param, stream, gloss in TARGETS:
        pts = series_from_records(obs, parameter=param, stream=stream)
        # One report per year: collapse duplicates by taking the most confident
        # reading, rather than letting a page that states a value twice weight it.
        best: dict[float, tuple[float, float, float]] = {}
        for y, v, c in pts:
            if y not in best or c > best[y][2]:
                best[y] = (y, v, c)
        pts = sorted(best.values())
        if len(pts) < 2:
            continue
        any_series = True
        label = f"{param}" + (f" ({stream})" if stream else "")
        print(f"\n{label}  — {gloss}")
        print("   " + "  ".join(f"{int(y)}:{v:g}" for y, v, _ in pts))
        t = trend(pts)
        print(f"   trend: {t.describe()}")
        if t.ok:
            print(f"   mean reading confidence {t.mean_confidence:.2f}")
        cp = changepoint([(y, v) for y, v, _ in pts])
        if cp.ok:
            verdict = "detected" if cp.detected else "not significant"
            print(f"   changepoint: {verdict} at {cp.at:.0f}, "
                  f"{cp.mean_before:.4g} -> {cp.mean_after:.4g} "
                  f"(shift {cp.shift:+.4g}, p={cp.p_value:.3f})")
            if not cp.detected:
                print("     note: Pettitt is very conservative at this n; a null "
                      "result here is not evidence of no change")

    if not any_series:
        print("  (no parameter yet has 2+ years — extraction still in progress)")

    print("\n--- most-measured parameters ---")
    c = collections.Counter(r.parameter.lower() for r in obs)
    for name, n in c.most_common(12):
        print(f"  {n:>3}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
