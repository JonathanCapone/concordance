"""Read many towns in sequence, unattended.

One GPU serves one job at a time, so this is deliberately serial rather than
parallel: running two extractions at once halves the speed of both and starves
anything else that wants the model.

Every town is resumable on its own, so killing this and restarting loses at most
the page in flight.

    python scripts/run_batch.py --towns 8
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from groundtruth.archive import Archive  # noqa: E402

PATTERNS = [
    re.compile(r"^(?P<p>.+?)\s*:\s*water pollution control plant", re.I),
    re.compile(r"\bon (?:the )?(?:city|town|village|township) of (?P<p>.+?)\s+water pollution", re.I),
    re.compile(r"\bon (?P<p>.+?)\s+water pollution control plant", re.I),
    re.compile(r"^(?P<p>.+?)\s+water pollution control plant", re.I),
]
NOISE = re.compile(r"^(annual report|report|operating summary|\d{4}|report on|operating cost|"
                   r"thirty|evaluation|expansion|ontario water resources)", re.I)


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
        if p and 3 <= len(p) <= 42 and not NOISE.match(p):
            return p.title()
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--towns", type=int, default=8)
    ap.add_argument("--model", default="gemma4:12b")
    ap.add_argument("--timeout", type=float, default=500.0)
    ap.add_argument("--skip-done", action="store_true", default=True)
    args = ap.parse_args()

    archive = Archive()
    counts: collections.Counter = collections.Counter()
    for item in archive.iter_items(title_contains="water pollution control plant"):
        place = place_of(str(item.get("title", "")))
        if place and item.get("year"):
            counts[place] += 1

    done = {p.stem.replace("-", " ").lower() for p in Path("data/results").glob("*.json")}
    # Most reports first: a town with twelve surviving years yields a series,
    # one with a single report yields a dot.
    queue = [(p, n) for p, n in counts.most_common() if p.lower() not in done][: args.towns]

    print(f"{len(queue)} towns queued (most reports first)\n")
    for place, n in queue:
        print(f"=== {place} ({n} reports) ===", flush=True)
        t0 = time.time()
        proc = subprocess.run(
            [sys.executable, "-u", "scripts/extract_place.py",
             "--place", place, "--title-filter", place.lower(),
             "--model", args.model, "--timeout", str(args.timeout)],
            capture_output=True, text=True,
        )
        tail = [ln for ln in (proc.stdout or "").splitlines() if "records" in ln][-1:]
        print(f"  {time.time()-t0:.0f}s  {tail[0].strip() if tail else 'no output'}", flush=True)
        if proc.returncode != 0:
            print(f"  FAILED rc={proc.returncode}: {(proc.stderr or '')[-200:]}", flush=True)

    print("\nbatch complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
