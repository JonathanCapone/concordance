"""Read many towns in sequence, unattended.

One GPU serves one job at a time, so this is deliberately serial rather than
parallel: running two extractions at once halves the speed of both and starves
anything else that wants the model.

Every town is resumable on its own, so killing this and restarting loses at most
the page in flight.  A result filename is not evidence that the town finished:
``extract_place.py`` writes that file after every page.  This runner records a
separate completion receipt only after a clean child-process exit and binds the
receipt to the exact result bytes and current catalogue count.

    python scripts/run_batch.py --towns 8
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from concordance.archive import Archive  # noqa: E402

PATTERNS = [
    re.compile(r"^(?P<p>.+?)\s*:\s*water pollution control plant", re.I),
    re.compile(r"\bon (?:the )?(?:city|town|village|township) of (?P<p>.+?)\s+water pollution", re.I),
    re.compile(r"\bon (?P<p>.+?)\s+water pollution control plant", re.I),
    re.compile(r"^(?P<p>.+?)\s+water pollution control plant", re.I),
]
NOISE = re.compile(r"^(annual report|report|operating summary|\d{4}|report on|operating cost|"
                   r"thirty|evaluation|expansion|ontario water resources)", re.I)
COMPLETION_SCHEMA = 1
COMPLETION_DIR = ".batch-complete"
FAILED_RUN = re.compile(r"\b(?:ERROR|FAILED)\b")
FINAL_SUMMARY = re.compile(r"\b(?P<records>\d+) records from (?P<reports>\d+) reports\s*$")


@dataclass(frozen=True)
class ResultSnapshot:
    """The minimum internally consistent evidence for one incremental result."""

    sha256: str
    n_records: int
    n_pages_attempted: int


@dataclass(frozen=True)
class BatchTown:
    place: str
    reports: int
    state: str
    result_path: Path
    rank: int
    modified_ns: int = 0


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


def slug_of(place: str) -> str:
    """Match the filename convention used by ``extract_place.py``."""
    return place.lower().replace(" ", "-")


def result_path_for(results_dir: Path, place: str) -> Path:
    return results_dir / f"{slug_of(place)}.json"


def completion_path_for(results_dir: Path, place: str) -> Path:
    # Keep receipts out of results_dir/*.json: older runners interpreted every
    # JSON stem there as the name of a finished town.
    return results_dir / COMPLETION_DIR / f"{slug_of(place)}.json"


def _same_place(left: object, right: str) -> bool:
    return isinstance(left, str) and " ".join(left.split()).casefold() == (
        " ".join(right.split()).casefold()
    )


def result_snapshot(path: Path, place: str) -> ResultSnapshot | None:
    """Return evidence only for a well-formed, internally consistent result.

    A parseable file alone is deliberately insufficient.  In particular, a
    killed extraction can contain hundreds of valid records and still be only a
    partial town.
    """
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not _same_place(payload.get("place"), place):
        return None
    records = payload.get("records")
    attempted = payload.get("pages_attempted")
    n_records = payload.get("n_records")
    if not isinstance(records, list) or not isinstance(attempted, list):
        return None
    if type(n_records) is not int or n_records != len(records):
        return None
    if not all(isinstance(key, str) and key for key in attempted):
        return None
    if len(set(attempted)) != len(attempted):
        return None
    return ResultSnapshot(
        sha256=hashlib.sha256(raw).hexdigest(),
        n_records=n_records,
        n_pages_attempted=len(attempted),
    )


def has_completion_receipt(results_dir: Path, place: str, reports: int) -> bool:
    """Whether a receipt still matches both the result and catalogue metadata."""
    result_path = result_path_for(results_dir, place)
    snapshot = result_snapshot(result_path, place)
    if snapshot is None:
        return False
    try:
        receipt = json.loads(completion_path_for(results_dir, place).read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(receipt, dict):
        return False
    expected = {
        "schema": COMPLETION_SCHEMA,
        "status": "complete",
        "place": place,
        "result": result_path.name,
        "result_sha256": snapshot.sha256,
        "n_records": snapshot.n_records,
        "n_pages_attempted": snapshot.n_pages_attempted,
        "catalog_report_count": reports,
    }
    return all(receipt.get(key) == value for key, value in expected.items())


def write_completion_receipt(
    results_dir: Path,
    place: str,
    catalog_reports: int,
    reports_read: int,
) -> ResultSnapshot:
    """Atomically record a clean run without modifying its incremental result."""
    result_path = result_path_for(results_dir, place)
    snapshot = result_snapshot(result_path, place)
    if snapshot is None:
        raise ValueError(f"{result_path} is missing or internally inconsistent")
    receipt_path = completion_path_for(results_dir, place)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema": COMPLETION_SCHEMA,
        "status": "complete",
        "place": place,
        "result": result_path.name,
        "result_sha256": snapshot.sha256,
        "n_records": snapshot.n_records,
        "n_pages_attempted": snapshot.n_pages_attempted,
        "catalog_report_count": catalog_reports,
        "reports_read": reports_read,
    }
    temporary = receipt_path.with_suffix(receipt_path.suffix + ".tmp")
    temporary.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    temporary.replace(receipt_path)
    return snapshot


def completed_reports(proc: subprocess.CompletedProcess[str]) -> int | None:
    """Extract completion evidence from a clean ``extract_place.py`` run.

    That script catches per-item and per-page failures so return code zero is
    not sufficient.  Its final summary plus the absence of ERROR/FAILED lines
    is the conservative boundary for writing a receipt.  A timeout that succeeds
    on the built-in retry is allowed because it has no FAILED line.
    """
    output = "\n".join(part for part in (proc.stdout or "", proc.stderr or "") if part)
    if proc.returncode != 0 or FAILED_RUN.search(output):
        return None
    summaries = [FINAL_SUMMARY.search(line) for line in output.splitlines()]
    matches = [match for match in summaries if match]
    return int(matches[-1].group("reports")) if matches else None


def plan_batch(
    counts: collections.Counter[str],
    results_dir: Path,
    towns: int,
    *,
    skip_done: bool,
) -> tuple[list[BatchTown], int]:
    """Plan resumptions before new towns, skipping only receipt-backed results.

    Legacy results have no completion receipt.  They are safe to resume because
    ``extract_place.py`` preserves their records and skips attempted pages.  The
    most recently modified legacy result runs first, which puts an interrupted
    in-flight town ahead of older, probably-finished legacy files.
    """
    candidates: list[BatchTown] = []
    skipped = 0
    for rank, (place, reports) in enumerate(counts.most_common()):
        result_path = result_path_for(results_dir, place)
        complete = has_completion_receipt(results_dir, place, reports)
        if skip_done and complete:
            skipped += 1
            continue
        if result_path.exists():
            try:
                modified_ns = result_path.stat().st_mtime_ns
            except OSError:
                modified_ns = 0
            if complete:
                state = "complete"
            elif result_snapshot(result_path, place) is None:
                # Do not hand a malformed or wrong-place file to extract_place:
                # its incremental writer could otherwise replace or mix it.
                state = "blocked-invalid"
            else:
                state = "resume-unverified"
        else:
            modified_ns = 0
            state = "new"
        candidates.append(BatchTown(place, reports, state, result_path, rank, modified_ns))

    candidates.sort(
        key=lambda town: (
            1 if town.state == "new" else 0,
            -town.modified_ns if town.state != "new" else town.rank,
            town.rank,
        )
    )
    return candidates[:towns], skipped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--towns", type=int, default=8)
    ap.add_argument("--model", default="gemma4:12b")
    ap.add_argument("--timeout", type=float, default=500.0)
    ap.add_argument(
        "--skip-done",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "skip only towns with a matching completion receipt (default); "
            "use --no-skip-done to verify them again"
        ),
    )
    args = ap.parse_args()
    if args.towns < 1:
        ap.error("--towns must be at least 1")

    archive = Archive()
    counts: collections.Counter = collections.Counter()
    for item in archive.iter_items(title_contains="water pollution control plant"):
        place = place_of(str(item.get("title", "")))
        if place and item.get("year"):
            counts[place] += 1

    results_dir = Path("data/results")
    queue, skipped = plan_batch(
        counts, results_dir, args.towns, skip_done=args.skip_done
    )
    resumptions = sum(town.state != "new" for town in queue)
    print(
        f"{len(queue)} towns queued ({resumptions} resumptions, "
        f"{len(queue) - resumptions} new; {skipped} receipt-backed towns skipped)\n"
    )
    unfinished = 0
    verified = 0
    for town in queue:
        place, n = town.place, town.reports
        print(f"=== {place} ({n} reports; {town.state}) ===", flush=True)
        if town.state == "blocked-invalid":
            unfinished += 1
            print(
                f"  not started: {town.result_path} is malformed or belongs to "
                "a different place; it was left untouched",
                flush=True,
            )
            continue
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
        reports_read = completed_reports(proc)
        if reports_read is None:
            unfinished += 1
            print("  not marked complete; a restart will resume this town", flush=True)
            continue
        try:
            snapshot = write_completion_receipt(
                results_dir, place, n, reports_read
            )
        except (OSError, ValueError) as exc:
            unfinished += 1
            print(f"  not marked complete: {exc}", flush=True)
            continue
        verified += 1
        print(
            f"  completion receipt recorded for {snapshot.n_records} records "
            f"and {snapshot.n_pages_attempted} attempted pages",
            flush=True,
        )

    if unfinished:
        print(f"\nbatch stopped with {unfinished} resumable town(s); {verified} verified complete")
        return 1
    print(f"\nbatch complete: {verified} town(s) verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
