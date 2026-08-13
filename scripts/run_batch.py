"""Read many towns in sequence, unattended.

One GPU serves one job at a time, so this is deliberately serial rather than
parallel: running two extractions at once halves the speed of both and starves
anything else that wants the model.

Every town is resumable on its own, so killing this and restarting loses at most
the page in flight.  A result filename is not evidence that the town finished:
``extract_place.py`` writes that file after every page.  This runner records a
separate completion receipt only after a clean child-process exit and binds the
receipt to the exact result bytes, extractor code, and ordered report selection.

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
from typing import Iterable, Mapping, Sequence

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
COMPLETION_SCHEMA = 2
COMPLETION_DIR = ".batch-complete"
FAILED_RUN = re.compile(r"\b(?:ERROR|FAILED)\b")
FINAL_SUMMARY = re.compile(r"\b(?P<records>\d+) records from (?P<reports>\d+) reports\s*$")
REPORT_SUMMARY = re.compile(
    r"^  (?P<identifier>\S+)\s+.*?:\s+\d+ pages,\s+\d+ prose(?:\s|$)"
)
EXTRACT_SCRIPT = Path(__file__).with_name("extract_place.py")
ARCHIVE_SOURCE = Path(__file__).resolve().parents[1] / "concordance" / "archive.py"
SELECTION_SOURCES = (EXTRACT_SCRIPT, ARCHIVE_SOURCE)


@dataclass(frozen=True)
class ResultSnapshot:
    """The minimum internally consistent evidence for one incremental result."""

    sha256: str
    n_records: int
    n_pages_attempted: int


@dataclass(frozen=True)
class CompletionEvidence:
    """What the child process says it actually finished in this invocation."""

    n_records: int
    report_identifiers: tuple[str, ...]


@dataclass(frozen=True)
class BatchTown:
    place: str
    report_identifiers: tuple[str, ...]
    state: str
    result_path: Path
    rank: int
    modified_ns: int = 0

    @property
    def reports(self) -> int:
        return len(self.report_identifiers)


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


def select_report_identifiers(
    items: Iterable[Mapping[str, object]],
    place: str,
    *,
    max_items: int = 0,
) -> tuple[str, ...]:
    """Reproduce ``extract_place.py``'s exact ordered item selection.

    This is intentionally byte-for-byte equivalent in its title query, year
    sort, annual-report filter, and optional truncation.  Completion also checks
    the identifiers printed by the child at runtime, so future drift between the
    two implementations fails closed instead of producing a false receipt.
    """
    title_filter = place.lower()
    selected = sorted(
        (
            item
            for item in items
            if title_filter in str(item.get("title", "")).lower()
        ),
        key=lambda item: str(item.get("year") or "9999"),
    )
    selected = [
        item
        for item in selected
        if "annual report" in str(item.get("title", "")).lower()
        or "sewage treatment plant" in str(item.get("title", "")).lower()
    ]
    if max_items:
        selected = selected[:max_items]
    # Match the child's required ``it["identifier"]`` access: bad catalogue
    # metadata blocks planning instead of silently fingerprinting a substitute.
    return tuple(str(item["identifier"]) for item in selected)


def selection_fingerprint(report_identifiers: Sequence[str]) -> str:
    """Hash an ordered selection; membership with a different order is different."""
    canonical = json.dumps(
        list(report_identifiers), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def extractor_fingerprint(paths: Sequence[Path] = SELECTION_SOURCES) -> str:
    """Fingerprint the child and its archive-selection implementation.

    ``select_report_identifiers`` is duplicated here only because the child is a
    separate long-running script.  Hashing both source files means a future
    change to either side invalidates old receipts; runtime identifier matching
    then proves the two implementations still agree before a new receipt exists.
    """
    digest = hashlib.sha256()
    for path in paths:
        raw = path.read_bytes()
        encoded_name = path.name.encode("utf-8")
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()


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


def has_completion_receipt(
    results_dir: Path,
    place: str,
    report_identifiers: Sequence[str],
    *,
    extractor_sha256: str | None = None,
) -> bool:
    """Whether a receipt matches the result, extractor, and exact selection."""
    result_path = result_path_for(results_dir, place)
    snapshot = result_snapshot(result_path, place)
    if snapshot is None:
        return False
    identifiers = tuple(report_identifiers)
    try:
        current_extractor = extractor_sha256 or extractor_fingerprint()
    except OSError:
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
        "extractor_sha256": current_extractor,
        "reports_read": len(identifiers),
        "report_identifiers": list(identifiers),
        "report_selection_sha256": selection_fingerprint(identifiers),
    }
    return all(receipt.get(key) == value for key, value in expected.items())


def write_completion_receipt(
    results_dir: Path,
    place: str,
    report_identifiers: Sequence[str],
    evidence: CompletionEvidence,
    *,
    extractor_sha256: str | None = None,
) -> ResultSnapshot:
    """Atomically record an exact clean run without modifying its result."""
    result_path = result_path_for(results_dir, place)
    snapshot = result_snapshot(result_path, place)
    if snapshot is None:
        raise ValueError(f"{result_path} is missing or internally inconsistent")
    expected_identifiers = tuple(report_identifiers)
    if evidence.report_identifiers != expected_identifiers:
        raise ValueError(
            "child report selection does not match the planned ordered selection"
        )
    if evidence.n_records != snapshot.n_records:
        raise ValueError(
            f"child reported {evidence.n_records} records but result has "
            f"{snapshot.n_records}"
        )
    current_extractor = extractor_sha256 or extractor_fingerprint()
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
        "extractor_sha256": current_extractor,
        "reports_read": len(expected_identifiers),
        "report_identifiers": list(expected_identifiers),
        "report_selection_sha256": selection_fingerprint(expected_identifiers),
    }
    temporary = receipt_path.with_suffix(receipt_path.suffix + ".tmp")
    temporary.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    temporary.replace(receipt_path)
    return snapshot


def completion_evidence(
    proc: subprocess.CompletedProcess[str],
) -> CompletionEvidence | None:
    """Extract completion evidence from a clean ``extract_place.py`` run.

    That script catches per-item and per-page failures so return code zero is
    not sufficient.  Its final summary plus the absence of ERROR/FAILED lines
    is the conservative boundary for writing a receipt.  A timeout that succeeds
    on the built-in retry is allowed because it has no FAILED line.
    """
    output = "\n".join(part for part in (proc.stdout or "", proc.stderr or "") if part)
    if proc.returncode != 0 or FAILED_RUN.search(output):
        return None
    lines = output.splitlines()
    summaries = [FINAL_SUMMARY.search(line) for line in lines]
    matches = [match for match in summaries if match]
    if not matches:
        return None
    summary = matches[-1]
    identifiers = tuple(
        match.group("identifier")
        for line in lines
        if (match := REPORT_SUMMARY.match(line))
    )
    if len(identifiers) != int(summary.group("reports")):
        return None
    return CompletionEvidence(
        n_records=int(summary.group("records")),
        report_identifiers=identifiers,
    )


def plan_batch(
    selections: Mapping[str, Sequence[str]],
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
    # More reports first, preserving discovery order for ties.
    ordered = sorted(selections.items(), key=lambda pair: -len(pair[1]))
    for rank, (place, report_identifiers) in enumerate(ordered):
        identifiers = tuple(report_identifiers)
        result_path = result_path_for(results_dir, place)
        complete = has_completion_receipt(results_dir, place, identifiers)
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
        candidates.append(
            BatchTown(place, identifiers, state, result_path, rank, modified_ns)
        )

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
    index = archive.load_index()
    counts: collections.Counter = collections.Counter()
    for item in index:
        if "water pollution control plant" not in str(item.get("title", "")).lower():
            continue
        place = place_of(str(item.get("title", "")))
        if place and item.get("year"):
            counts[place] += 1

    # Discovery is deliberately narrow, but the child query is broader: it may
    # also select sewage-treatment or drinking-water annual reports bearing the
    # town name.  Build the receipt contract from the child's exact selection,
    # not from the discovery counts (which differ substantially for some towns).
    selections = {
        place: select_report_identifiers(index, place)
        for place, _ in counts.most_common()
    }

    results_dir = Path("data/results")
    queue, skipped = plan_batch(
        selections, results_dir, args.towns, skip_done=args.skip_done
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
        try:
            extractor_before = extractor_fingerprint()
        except OSError as exc:
            unfinished += 1
            print(f"  not started: cannot fingerprint extractor ({exc})", flush=True)
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
        evidence = completion_evidence(proc)
        if evidence is None:
            unfinished += 1
            print("  not marked complete; a restart will resume this town", flush=True)
            continue
        try:
            extractor_after = extractor_fingerprint()
            if extractor_after != extractor_before:
                raise ValueError("extractor changed while the child was running")
            current_selection = select_report_identifiers(archive.load_index(), place)
            if current_selection != town.report_identifiers:
                raise ValueError("archive report selection changed while the child was running")
            snapshot = write_completion_receipt(
                results_dir,
                place,
                town.report_identifiers,
                evidence,
                extractor_sha256=extractor_before,
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
