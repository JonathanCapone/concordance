"""Read many towns in sequence, unattended.

One GPU serves one job at a time, so this is deliberately serial rather than
parallel: running two extractions at once halves the speed of both and starves
anything else that wants the model.

Every town is resumable on its own, so killing this and restarting loses at most
the page in flight.  A result filename is not evidence that the town finished:
``extract_place.py`` writes that file after every page.  This runner records a
separate completion receipt only after a clean child-process exit and binds the
receipt to the exact result bytes and ordered report selection.  A receipt says
that selection completed; it does not claim that a later code revision reread
pages already recorded in ``pages_attempted``.  A pre-existing legacy result
can never gain that receipt retroactively; after one clean incremental pass it
gets a separate scheduling checkpoint so it does not starve new towns.

    python scripts/run_batch.py --towns 8
"""

from __future__ import annotations

import argparse
import collections
from contextlib import contextmanager
import errno
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable, Iterator, Mapping, Sequence

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
MANAGED_RUN_SCHEMA = 1
MANAGED_RUN_DIR = ".batch-runs"
LEGACY_PASS_SCHEMA = 1
LEGACY_PASS_DIR = ".batch-legacy-passes"
RUN_LEASE_PREFIX = "groundtruth-run-batch"
FAILED_RUN = re.compile(r"\b(?:ERROR|FAILED)\b")
FINAL_SUMMARY = re.compile(r"\b(?P<records>\d+) records from (?P<reports>\d+) reports\s*$")
REPORT_SUMMARY = re.compile(
    r"^  (?P<identifier>\S+)\s+.*?:\s+"
    r"(?P<pages>\d+) pages,\s+\d+ prose(?:\s|$)"
)


@dataclass(frozen=True)
class ResultSnapshot:
    """The minimum internally consistent evidence for one incremental result."""

    sha256: str
    n_records: int
    n_pages_attempted: int


@dataclass(frozen=True)
class CompletionEvidence:
    """What the incremental child traversed and summarized in this invocation."""

    n_records: int
    report_identifiers: tuple[str, ...]
    report_page_counts: tuple[int, ...]


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


class BatchRunActiveError(RuntimeError):
    """Another process already owns the batch runner for this result tree."""


def batch_lease_path(results_dir: Path) -> Path:
    """Return the process-lock path for one resolved result directory.

    The lease lives in the operating-system temporary directory rather than
    under ``data/results``.  It is runtime coordination, not resumable result
    provenance, and therefore must never look like a completion marker.
    """
    resolved = os.path.normcase(str(results_dir.resolve(strict=False)))
    digest = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:24]
    return Path(tempfile.gettempdir()) / f"{RUN_LEASE_PREFIX}-{digest}.lock"


def _lock_lease(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_lease(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def batch_run_lease(results_dir: Path) -> Iterator[Path]:
    """Hold the one process-level lease for ``results_dir``.

    The kernel lock, not the file contents, is authoritative.  Closing the
    handle releases it even after an unhandled exception or process crash, so a
    stale lock file is harmless and recoverable on Windows without guessing
    whether a recorded PID has been reused.
    """
    path = batch_lease_path(results_dir)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    handle = os.fdopen(descriptor, "r+b", buffering=0)
    locked = False
    try:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"\0")
        try:
            _lock_lease(handle)
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                raise
            raise BatchRunActiveError(
                f"another run_batch process already owns {results_dir.resolve(strict=False)}; "
                "no town was started"
            ) from exc
        locked = True
        metadata = json.dumps(
            {
                "pid": os.getpid(),
                "acquired_at_unix": time.time(),
                "results_dir": str(results_dir.resolve(strict=False)),
            },
            sort_keys=True,
        ).encode("utf-8")
        handle.seek(0)
        handle.write(metadata)
        handle.truncate()
        yield path
    finally:
        try:
            if locked:
                _unlock_lease(handle)
        finally:
            handle.close()


def extraction_command(town: BatchTown, model: str, timeout: float) -> list[str]:
    """Build the child command, explicitly pinning its safe planned result path."""
    return [
        sys.executable,
        "-u",
        "scripts/extract_place.py",
        "--place",
        town.place,
        "--title-filter",
        town.place.lower(),
        "--model",
        model,
        "--timeout",
        str(timeout),
        "--out",
        str(town.result_path),
    ]


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


_WINDOWS_DEVICE_STEMS = {
    "con", "prn", "aux", "nul", "clock$",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}
# Preserve the historical extractor filename for any place whose old slug was
# already a safe Windows filename. Punctuation such as the period in
# ``Sault Ste. Marie`` is harmless and changing that stem would strand an
# existing result under a new name.
_SAFE_HISTORICAL_SLUG = re.compile(r"[a-z0-9][a-z0-9._-]{0,99}\Z")


def _canonical_place(place: str) -> str:
    if not isinstance(place, str):
        raise TypeError("place must be a string")
    canonical = " ".join(unicodedata.normalize("NFKC", place).split())
    if not canonical:
        raise ValueError("place must contain a visible character")
    return canonical


def slug_of(place: str) -> str:
    """Return a deterministic Windows-safe filename stem for ``place``.

    Existing ordinary names retain the historical lower-case, hyphenated stem.
    Names that need escaping receive a readable ASCII prefix plus a digest of
    the complete canonical name, so punctuation cannot collapse two places to
    one path.  Planning separately rejects even the remote possibility of a
    digest collision.
    """
    canonical = _canonical_place(place)
    historical = canonical.lower().replace(" ", "-")
    historical_stem = historical.split(".", 1)[0]
    if (not historical.endswith((".", " "))
            and _SAFE_HISTORICAL_SLUG.fullmatch(historical)
            and historical_stem not in _WINDOWS_DEVICE_STEMS):
        return historical

    decomposed = unicodedata.normalize("NFKD", canonical.casefold())
    ascii_name = decomposed.encode("ascii", "ignore").decode("ascii")
    readable = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")
    readable = readable[:60].rstrip("-") or "place"
    digest = hashlib.sha256(canonical.casefold().encode("utf-8")).hexdigest()[:16]
    return f"{readable}--{digest}"


def _contained_path(results_dir: Path, *parts: str) -> Path:
    """Build a path and fail closed if a symlink or component escapes the root."""
    root = results_dir.resolve(strict=False)
    candidate = root.joinpath(*parts).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"batch path escapes results directory: {candidate}") from exc
    return candidate


def _temporary_path(results_dir: Path, target: Path) -> Path:
    temporary = target.with_name(target.name + ".tmp")
    root = results_dir.resolve(strict=False)
    try:
        temporary.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise ValueError(f"temporary path escapes results directory: {temporary}") from exc
    return temporary


def result_path_for(results_dir: Path, place: str) -> Path:
    return _contained_path(results_dir, f"{slug_of(place)}.json")


def completion_path_for(results_dir: Path, place: str) -> Path:
    # Keep receipts out of results_dir/*.json: older runners interpreted every
    # JSON stem there as the name of a finished town.
    return _contained_path(results_dir, COMPLETION_DIR, f"{slug_of(place)}.json")


def managed_run_path_for(results_dir: Path, place: str) -> Path:
    return _contained_path(results_dir, MANAGED_RUN_DIR, f"{slug_of(place)}.json")


def legacy_pass_path_for(results_dir: Path, place: str) -> Path:
    return _contained_path(results_dir, LEGACY_PASS_DIR, f"{slug_of(place)}.json")


def prepare_managed_run(
    results_dir: Path,
    place: str,
    report_identifiers: Sequence[str],
) -> bool:
    """Whether this result began under the receipt-aware runner.

    A legacy ``pages_attempted`` ledger cannot prove those pages were actually
    traversed because the child trusts and skips it. Only a marker created while
    no result existed can bridge an interrupted receipt-aware run. Old results
    may still resume, but remain receipt-ineligible until a fresh extraction.
    """
    marker_path = managed_run_path_for(results_dir, place)
    identifiers = tuple(report_identifiers)
    expected = {
        "schema": MANAGED_RUN_SCHEMA,
        "place": place,
        "result": result_path_for(results_dir, place).name,
        "report_identifiers": list(identifiers),
        "report_selection_sha256": selection_fingerprint(identifiers),
    }
    try:
        marker = json.loads(marker_path.read_text("utf-8"))
    except FileNotFoundError:
        marker = None
    except (OSError, json.JSONDecodeError):
        return False
    if marker is not None:
        return isinstance(marker, dict) and all(
            marker.get(key) == value for key, value in expected.items()
        )
    if result_path_for(results_dir, place).exists():
        return False
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(results_dir, marker_path)
    temporary.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    temporary.replace(marker_path)
    return True


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


def _same_place(left: object, right: str) -> bool:
    return isinstance(left, str) and " ".join(left.split()).casefold() == (
        " ".join(right.split()).casefold()
    )


def result_snapshot(
    path: Path,
    place: str,
    report_identifiers: Sequence[str] | None = None,
) -> ResultSnapshot | None:
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
    if report_identifiers is not None:
        allowed = set(report_identifiers)
        if not allowed:
            return None
        # ``extract_place`` trusts pages_attempted as its resume ledger. Bind
        # every skipped page to the exact planned report set before that ledger
        # can support a completion receipt. A predeclared or broader legacy key
        # must block, not silently skip work and acquire a narrower receipt.
        for key in attempted:
            identifier, separator, page = key.rpartition("#")
            if (not separator or identifier not in allowed or
                    not page.isdigit() or int(page) < 1):
                return None
        # The result bytes must describe only the reports the receipt names.
        # Child stdout proves traversal; provenance membership proves content.
        for record in records:
            if not isinstance(record, dict):
                return None
            provenance = record.get("provenance")
            if not isinstance(provenance, dict):
                return None
            if provenance.get("identifier") not in allowed:
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
) -> bool:
    """Whether a receipt matches the result and exact ordered selection.

    Receipts intentionally do not encode extractor-source provenance.  The
    extractor resumes from ``pages_attempted``; changing its code does not cause
    old pages to be read again and therefore cannot honestly supersede a valid
    completion receipt without a separate fresh-extraction mode.
    """
    result_path = result_path_for(results_dir, place)
    snapshot = result_snapshot(result_path, place, report_identifiers)
    if snapshot is None:
        return False
    identifiers = tuple(report_identifiers)
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
        "reports_read": len(identifiers),
        "report_identifiers": list(identifiers),
        "report_selection_sha256": selection_fingerprint(identifiers),
    }
    return all(receipt.get(key) == value for key, value in expected.items())


def has_legacy_pass_checkpoint(
    results_dir: Path,
    place: str,
    report_identifiers: Sequence[str],
) -> bool:
    """Whether an old result has since completed one clean incremental pass.

    This is deliberately separate from a completion receipt.  It only settles
    scheduling: the child made a clean pass over the exact current selection,
    but may have trusted pages recorded before receipt-aware management began.
    It is therefore neither fresh verification nor receipt-backed evidence.
    """
    result_path = result_path_for(results_dir, place)
    snapshot = result_snapshot(result_path, place, report_identifiers)
    if snapshot is None:
        return False
    identifiers = tuple(report_identifiers)
    try:
        checkpoint = json.loads(
            legacy_pass_path_for(results_dir, place).read_text("utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(checkpoint, dict):
        return False
    expected = {
        "schema": LEGACY_PASS_SCHEMA,
        "status": "clean-incremental-pass-only",
        "receipt_backed": False,
        "fresh_verification": False,
        "place": place,
        "result": result_path.name,
        "result_sha256": snapshot.sha256,
        "n_records": snapshot.n_records,
        "n_pages_attempted": snapshot.n_pages_attempted,
        "reports_seen": len(identifiers),
        "report_identifiers": list(identifiers),
        "report_selection_sha256": selection_fingerprint(identifiers),
    }
    return all(checkpoint.get(key) == value for key, value in expected.items())


def _validate_completion_evidence(
    expected_identifiers: tuple[str, ...],
    evidence: CompletionEvidence,
) -> None:
    if evidence.report_identifiers != expected_identifiers:
        raise ValueError(
            "child report selection does not match the planned ordered selection"
        )
    if len(evidence.report_page_counts) != len(expected_identifiers):
        raise ValueError("child did not report a page count for every selected report")
    if any(type(pages) is not int or pages < 1 for pages in evidence.report_page_counts):
        raise ValueError("child reported a nonterminal zero-page report")


def write_legacy_pass_checkpoint(
    results_dir: Path,
    place: str,
    report_identifiers: Sequence[str],
    evidence: CompletionEvidence,
) -> ResultSnapshot:
    """Settle an unmanaged result after a clean pass, without issuing a receipt."""
    expected_identifiers = tuple(report_identifiers)
    _validate_completion_evidence(expected_identifiers, evidence)
    result_path = result_path_for(results_dir, place)
    snapshot = result_snapshot(result_path, place, expected_identifiers)
    if snapshot is None:
        raise ValueError(f"{result_path} is missing or internally inconsistent")
    if evidence.n_records != snapshot.n_records:
        raise ValueError(
            f"child reported {evidence.n_records} records but result has "
            f"{snapshot.n_records}"
        )
    checkpoint_path = legacy_pass_path_for(results_dir, place)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "schema": LEGACY_PASS_SCHEMA,
        "status": "clean-incremental-pass-only",
        "receipt_backed": False,
        "fresh_verification": False,
        "place": place,
        "result": result_path.name,
        "result_sha256": snapshot.sha256,
        "n_records": snapshot.n_records,
        "n_pages_attempted": snapshot.n_pages_attempted,
        "reports_seen": len(expected_identifiers),
        "report_identifiers": list(expected_identifiers),
        "report_selection_sha256": selection_fingerprint(expected_identifiers),
    }
    temporary = _temporary_path(results_dir, checkpoint_path)
    temporary.write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")
    temporary.replace(checkpoint_path)
    return snapshot


def write_completion_receipt(
    results_dir: Path,
    place: str,
    report_identifiers: Sequence[str],
    evidence: CompletionEvidence,
) -> ResultSnapshot:
    """Atomically record an exact clean incremental pass and its result."""
    expected_identifiers = tuple(report_identifiers)
    _validate_completion_evidence(expected_identifiers, evidence)
    result_path = result_path_for(results_dir, place)
    snapshot = result_snapshot(result_path, place, expected_identifiers)
    if snapshot is None:
        raise ValueError(f"{result_path} is missing or internally inconsistent")
    if evidence.n_records != snapshot.n_records:
        raise ValueError(
            f"child reported {evidence.n_records} records but result has "
            f"{snapshot.n_records}"
        )
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
        "reports_read": len(expected_identifiers),
        "report_identifiers": list(expected_identifiers),
        "report_selection_sha256": selection_fingerprint(expected_identifiers),
    }
    temporary = _temporary_path(results_dir, receipt_path)
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
    report_matches = tuple(
        match
        for line in lines
        if (match := REPORT_SUMMARY.match(line))
    )
    if len(report_matches) != int(summary.group("reports")):
        return None
    page_counts = tuple(int(match.group("pages")) for match in report_matches)
    if any(pages < 1 for pages in page_counts):
        return None
    return CompletionEvidence(
        n_records=int(summary.group("records")),
        report_identifiers=tuple(
            match.group("identifier") for match in report_matches
        ),
        report_page_counts=page_counts,
    )


def plan_batch(
    selections: Mapping[str, Sequence[str]],
    results_dir: Path,
    towns: int,
    *,
    skip_done: bool,
) -> tuple[list[BatchTown], int]:
    """Plan resumptions before new towns, skipping settled results.

    Legacy results have no completion receipt.  They are safe to resume because
    ``extract_place.py`` preserves their records and skips attempted pages.  The
    first clean legacy pass writes a separate, explicitly non-receipt checkpoint
    so it cannot requeue forever.  The most recently modified unsettled legacy
    result runs first, which puts an interrupted in-flight town ahead of older
    legacy files.
    """
    candidates: list[BatchTown] = []
    skipped = 0
    slugs: dict[str, str] = {}
    for place in selections:
        slug = slug_of(place)
        previous = slugs.get(slug)
        if previous is not None and previous != place:
            raise ValueError(
                f"places {previous!r} and {place!r} map to the same batch slug "
                f"{slug!r}"
            )
        slugs[slug] = place
    # More reports first, preserving discovery order for ties.
    ordered = sorted(selections.items(), key=lambda pair: -len(pair[1]))
    for rank, (place, report_identifiers) in enumerate(ordered):
        identifiers = tuple(report_identifiers)
        result_path = result_path_for(results_dir, place)
        complete = has_completion_receipt(results_dir, place, identifiers)
        legacy_pass = has_legacy_pass_checkpoint(results_dir, place, identifiers)
        if skip_done and (complete or legacy_pass):
            skipped += 1
            continue
        if result_path.exists():
            try:
                modified_ns = result_path.stat().st_mtime_ns
            except OSError:
                modified_ns = 0
            if complete:
                state = "receipt-backed"
            elif legacy_pass:
                state = "legacy-pass-observed"
            elif result_snapshot(result_path, place, identifiers) is None:
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
            "skip towns with a matching completion receipt or explicit legacy "
            "incremental-pass checkpoint (default); --no-skip-done includes "
            "them in the incremental pass but does not reread pages already "
            "attempted"
        ),
    )
    args = ap.parse_args()
    if args.towns < 1:
        ap.error("--towns must be at least 1")

    results_dir = Path("data/results")
    try:
        with batch_run_lease(results_dir):
            return _run_planned_batch(args, results_dir)
    except BatchRunActiveError as exc:
        print(f"batch not started: {exc}", file=sys.stderr, flush=True)
        return 2


def _run_planned_batch(args: argparse.Namespace, results_dir: Path) -> int:

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

    queue, skipped = plan_batch(
        selections, results_dir, args.towns, skip_done=args.skip_done
    )
    resumptions = sum(town.state == "resume-unverified" for town in queue)
    included = sum(town.state == "receipt-backed" for town in queue)
    legacy_included = sum(town.state == "legacy-pass-observed" for town in queue)
    blocked = sum(town.state == "blocked-invalid" for town in queue)
    new = sum(town.state == "new" for town in queue)
    print(
        f"{len(queue)} towns queued ({resumptions} resumable, {included} "
        f"receipt-backed included, {legacy_included} legacy-pass included, "
        f"{new} new, {blocked} blocked; {skipped} settled towns skipped)\n"
    )
    unfinished = 0
    receipts_recorded = 0
    legacy_passes_recorded = 0
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
        receipt_eligible = town.state == "receipt-backed" or prepare_managed_run(
            results_dir, place, town.report_identifiers,
        )
        if not receipt_eligible:
            print(
                "  legacy/unmanaged progress may resume, but cannot earn a "
                "completion receipt without a fresh managed extraction",
                flush=True,
            )
        t0 = time.time()
        proc = subprocess.run(
            extraction_command(town, args.model, args.timeout),
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
            current_selection = select_report_identifiers(archive.load_index(), place)
            if current_selection != town.report_identifiers:
                raise ValueError("archive report selection changed while the child was running")
            if receipt_eligible:
                snapshot = write_completion_receipt(
                    results_dir,
                    place,
                    town.report_identifiers,
                    evidence,
                )
            else:
                snapshot = write_legacy_pass_checkpoint(
                    results_dir,
                    place,
                    town.report_identifiers,
                    evidence,
                )
        except (OSError, ValueError) as exc:
            unfinished += 1
            print(f"  not marked complete: {exc}", flush=True)
            continue
        if receipt_eligible:
            receipts_recorded += 1
            try:
                managed_run_path_for(results_dir, place).unlink()
            except FileNotFoundError:
                pass
            print(
                f"  completion receipt recorded for {snapshot.n_records} records "
                f"and {snapshot.n_pages_attempted} attempted pages",
                flush=True,
            )
        else:
            legacy_passes_recorded += 1
            print(
                "  legacy incremental-pass checkpoint recorded for "
                f"{snapshot.n_records} records; this is not a completion "
                "receipt or fresh verification",
                flush=True,
            )

    if unfinished:
        print(
            f"\nbatch stopped with {unfinished} unfinished town(s); "
            f"{receipts_recorded} completion receipt(s) and "
            f"{legacy_passes_recorded} legacy pass checkpoint(s) recorded"
        )
        return 1
    print(
        f"\nbatch complete: {receipts_recorded} completion receipt(s) and "
        f"{legacy_passes_recorded} legacy pass checkpoint(s) recorded"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
