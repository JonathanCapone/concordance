"""Measure deterministic publication-year recovery from cached archive OCR.

This is a validation run before it is a catalogue-repair run.  It draws one
fixed sample from the year-less residue that title/date repair could not solve,
and a second fixed sample whose known catalogue years are hidden.  Both samples
are frozen into the output before the first OCR request, so an interruption can
resume without quietly changing the experiment.

Nothing here edits Internet Archive metadata.  Every recovered year remains a
reviewable proposal with the exact OCR evidence that produced it.

    python scripts/recover_years.py --sample 300 --validation-sample 300
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


SCHEMA_VERSION = 2
# The acceptance experiment is large and resumable, but its checkpoint is a
# generated measurement rather than a committed corpus artifact.  Keep the
# default under the repository's ignored cache boundary.
DEFAULT_OUT = "data/cache/dating/year_recovery.json"
HIGH_CONFIDENCE = 0.85
MEDIUM_CONFIDENCE = 0.65
DEFAULT_VALIDATION_SEED = 20260812

# The first detector was calibrated against this fixed cohort. A final accuracy
# claim must not reuse those answers or close editions of the same serial.
CALIBRATION_SEED = 4242
CALIBRATION_UNKNOWN_SAMPLE = 300
CALIBRATION_VALIDATION_SAMPLE = 300


def _detector_fingerprint() -> str:
    """Hash dating source so a resumed run cannot mix detector revisions."""
    source = Path(__file__).resolve().parents[1] / "groundtruth" / "dating.py"
    return hashlib.sha256(source.read_bytes()).hexdigest()


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=(
            "Recover publication years from OCR and measure exact accuracy on "
            "a held-out sample of items with known catalogue years."
        )
    )
    ap.add_argument(
        "--sample",
        "--unknown-sample",
        dest="unknown_sample",
        type=int,
        default=300,
        help=(
            "year-less items to sample from the title/date-repair residue "
            "(default: 300)"
        ),
    )
    ap.add_argument(
        "--validation-sample",
        type=int,
        default=300,
        help=(
            "known-year items to mask and test, excluding metadata-inferable "
            "items (default: 300)"
        ),
    )
    ap.add_argument("--seed", type=int, default=4242, help="sampling seed (default: 4242)")
    ap.add_argument(
        "--validation-seed",
        type=int,
        default=DEFAULT_VALIDATION_SEED,
        help=(
            "separate seed for the calibration-disjoint known-year evaluation "
            f"(default: {DEFAULT_VALIDATION_SEED})"
        ),
    )
    ap.add_argument(
        "--sleep",
        type=float,
        default=0.4,
        help="quiet time between Archive OCR calls in seconds (default: 0.4)",
    )
    ap.add_argument(
        "--checkpoint-every",
        type=int,
        default=1,
        help="atomically save after this many attempted items (default: 1)",
    )
    ap.add_argument("--cache-dir", default="data/cache", help="Archive cache directory")
    ap.add_argument("--out", default=DEFAULT_OUT, help="checkpoint and final JSON path")
    ap.add_argument(
        "--fresh",
        action="store_true",
        help="start a new fixed sample even if --out already exists",
    )
    return ap


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    """Publish one complete checkpoint; never leave a half-written JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _positive_year(value: Any) -> int | None:
    """A usable held-out catalogue year, rejecting bool and the 16 zero rows."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    return None


def _masked(item: dict[str, Any]) -> dict[str, Any]:
    out = dict(item)
    out["year"] = None
    return out


def _title_family(item: dict[str, Any]) -> str:
    """A coarse serial key used only to keep calibration out of evaluation."""
    raw = item.get("title")
    if isinstance(raw, list):
        title = " ".join(str(part) for part in raw)
    else:
        title = str(raw or "")
    title = re.sub(r"\d+", " ", title.casefold())
    return re.sub(r"[^a-z]+", " ", title).strip()


def _new_state(
    index: list[dict[str, Any]],
    *,
    unknown_n: int,
    validation_n: int,
    seed: int,
    validation_seed: int = DEFAULT_VALIDATION_SEED,
    collection: str,
    metadata_infer: Callable[[dict[str, Any]], Any],
) -> dict[str, Any]:
    """Freeze both unbiased samples before any OCR fetch can succeed or fail."""
    yearless = [item for item in index if not item.get("year")]
    unknown_pool = [item for item in yearless if metadata_infer(item).year is None]

    known_positive: list[tuple[dict[str, Any], int]] = []
    validation_pool: list[tuple[dict[str, Any], int]] = []
    for item in index:
        expected = _positive_year(item.get("year"))
        if expected is None:
            continue
        known_positive.append((item, expected))
        hidden = _masked(item)
        if metadata_infer(hidden).year is None:
            validation_pool.append((hidden, expected))

    if unknown_n > len(unknown_pool):
        raise ValueError(
            f"requested {unknown_n} year-less items, but the repair residue has "
            f"only {len(unknown_pool)}"
        )
    unknown = [
        dict(item) for item in random.Random(seed).sample(unknown_pool, unknown_n)
    ]

    # Reconstruct the exact 300-item cohort used while designing the heuristics,
    # then exclude it and every normalized title family it contained.  On tiny
    # injected test corpora there is no prior calibration cohort to reconstruct.
    calibration_ids: set[str] = set()
    calibration_families: set[str] = set()
    calibration_applied = False
    if (
        len(unknown_pool) >= CALIBRATION_UNKNOWN_SAMPLE
        and len(validation_pool)
        >= CALIBRATION_VALIDATION_SAMPLE + validation_n
    ):
        calibration_applied = True
        calibration_rng = random.Random(CALIBRATION_SEED)
        calibration_rng.sample(unknown_pool, CALIBRATION_UNKNOWN_SAMPLE)
        calibration = calibration_rng.sample(
            validation_pool, CALIBRATION_VALIDATION_SAMPLE
        )
        calibration_ids = {str(item["identifier"]) for item, _ in calibration}
        calibration_families = {
            family for item, _ in calibration if (family := _title_family(item))
        }

    evaluation_pool = [
        pair
        for pair in validation_pool
        if str(pair[0]["identifier"]) not in calibration_ids
        and (
            not _title_family(pair[0])
            or _title_family(pair[0]) not in calibration_families
        )
    ]
    if validation_n > len(evaluation_pool):
        raise ValueError(
            f"requested {validation_n} validation items, but only "
            f"{len(evaluation_pool)} remain after calibration and title-family "
            "exclusion"
        )
    validation = [
        {"item": dict(item), "expected_year": expected}
        for item, expected in random.Random(validation_seed).sample(
            evaluation_pool, validation_n
        )
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "detector_sha256": _detector_fingerprint(),
        "collection": collection,
        "note": (
            "Proposals, not catalogue edits. Every guess must quote verbatim OCR. "
            "Validation years were hidden before inference and were not recoverable "
            "by the existing title/date pass. Exact accuracy measures agreement "
            "with a noisy catalogue surrogate, not unquestionable physical truth. "
            "On the full corpus, the evaluation excludes the calibration cohort "
            "and its title families."
        ),
        "sampling": {
            "seed": seed,
            "validation_seed": validation_seed,
            "unknown_sample": unknown_n,
            "validation_sample": validation_n,
            "unknown_population": "year-less and not inferable from title/date",
            "validation_population": (
                "positive known year, masked, not inferable from title/date, and "
                "disjoint from calibration identifiers and title families"
                if calibration_applied
                else "positive known year, masked, and not inferable from title/date"
            ),
        },
        "population": {
            "index_items": len(index),
            "yearless_items": len(yearless),
            "repair_residual_items": len(unknown_pool),
            "known_positive_year_items": len(known_positive),
            "validation_residual_items": len(validation_pool),
            "validation_calibration_items_excluded": len(calibration_ids),
            "validation_calibration_title_families": len(calibration_families),
            "validation_calibration_exclusion_applied": calibration_applied,
            "validation_evaluation_items": len(evaluation_pool),
        },
        "selected": {"unknown": unknown, "validation": validation},
        "results": {"unknown": {}, "validation": {}},
        "summary": {},
    }


def _load_state(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"{path} is not a recover_years schema-{SCHEMA_VERSION} checkpoint"
        )
    for key in ("sampling", "selected", "results"):
        if not isinstance(payload.get(key), dict):
            raise ValueError(f"{path} has no valid {key!r} object")
    return payload


def _check_resume(state: dict[str, Any], args: argparse.Namespace) -> None:
    saved_fingerprint = state.get("detector_sha256")
    current_fingerprint = _detector_fingerprint()
    if saved_fingerprint != current_fingerprint:
        raise ValueError(
            "dating detector changed since this checkpoint was created; use "
            "another --out path or pass --fresh"
        )
    sampling = state["sampling"]
    expected = {
        "seed": args.seed,
        "validation_seed": args.validation_seed,
        "unknown_sample": args.unknown_sample,
        "validation_sample": args.validation_sample,
    }
    mismatch = {
        key: (sampling.get(key), value)
        for key, value in expected.items()
        if sampling.get(key) != value
    }
    if mismatch:
        detail = ", ".join(
            f"{key}: checkpoint={old!r}, requested={new!r}"
            for key, (old, new) in mismatch.items()
        )
        raise ValueError(
            f"sampling options do not match the existing checkpoint ({detail}); "
            "use another --out path or pass --fresh"
        )


class _PoliteDelay:
    """Leave a quiet interval after one archive request before the next."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self._last_finished: float | None = None

    def wait(self) -> None:
        if self._last_finished is None or self.seconds <= 0:
            return
        elapsed = time.monotonic() - self._last_finished
        if elapsed < self.seconds:
            time.sleep(self.seconds - elapsed)

    def finished(self) -> None:
        self._last_finished = time.monotonic()


def _confidence_band(confidence: float) -> str:
    if confidence >= HIGH_CONFIDENCE:
        return "high (>=0.85)"
    if confidence >= MEDIUM_CONFIDENCE:
        return "medium (0.65-0.8499)"
    return "low (<0.65)"


def _safe_guess(
    item: dict[str, Any],
    text: str,
    infer_text: Callable[[dict[str, Any], str], Any],
) -> dict[str, Any]:
    """Infer once, rejecting any proposal that cannot quote its own source."""
    guess = infer_text(dict(item), text)
    data = guess.to_dict()
    year = data.get("year")
    if year is not None:
        evidence = data.get("evidence")
        confidence = data.get("confidence")
        if not isinstance(evidence, str) or not evidence or evidence not in text:
            return {
                "status": "invalid",
                "error": "dating returned a non-verbatim or empty evidence string",
                "guess": data,
            }
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(float(confidence))
            or not 0.0 <= float(confidence) <= 1.0
        ):
            return {
                "status": "invalid",
                "error": "dating returned confidence outside 0..1",
                "guess": data,
            }
    return {"status": "guessed" if year is not None else "abstained", "guess": data}


def _one_result(
    archive: Any,
    item: dict[str, Any],
    infer_text: Callable[[dict[str, Any], str], Any],
    delay: _PoliteDelay,
) -> dict[str, Any]:
    identifier = str(item.get("identifier") or "")
    base: dict[str, Any] = {"identifier": identifier, "title": item.get("title")}

    # A cold ocr_text() performs two HTTP requests internally: metadata, then
    # the text file.  Prime metadata explicitly so the same delay separates
    # those requests as well as consecutive items.  On a warm cache these are
    # cheap local reads; correctness is preferable to guessing which internal
    # Archive path will touch the network.
    delay.wait()
    try:
        archive.metadata(identifier)
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # noqa: BLE001 - preserve a large batch past one bad item
        return {
            **base,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        delay.finished()

    delay.wait()
    try:
        text = archive.ocr_text(identifier)
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # noqa: BLE001 - preserve a large batch past one bad item
        return {
            **base,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        delay.finished()

    if text is None:
        return {**base, "status": "no_ocr"}
    if not text.strip():
        return {**base, "status": "empty_ocr"}
    try:
        inferred = _safe_guess(item, text, infer_text)
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # noqa: BLE001 - report deterministic parser failures too
        return {
            **base,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {**base, **inferred}


def _completed(result: Any) -> bool:
    """Transient fetch/parser errors are retried on resume; final outcomes are not."""
    return isinstance(result, dict) and result.get("status") not in (None, "error")


def _guesses(results: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for result in results:
        if result.get("status") == "guessed" and isinstance(result.get("guess"), dict):
            yield result


def _breakdown(
    results: list[dict[str, Any]], *, validation: bool
) -> dict[str, Any]:
    by_basis: dict[str, dict[str, int]] = {}
    by_band: dict[str, dict[str, int]] = {}
    for result in _guesses(results):
        guess = result["guess"]
        basis = str(guess.get("basis") or "unspecified")
        band = _confidence_band(float(guess.get("confidence") or 0.0))
        basis_row = by_basis.setdefault(basis, {"guessed": 0, "correct": 0})
        band_row = by_band.setdefault(band, {"guessed": 0, "correct": 0})
        basis_row["guessed"] += 1
        band_row["guessed"] += 1
        if validation and result.get("correct") is True:
            basis_row["correct"] += 1
            band_row["correct"] += 1

    for group in (by_basis, by_band):
        for row in group.values():
            if validation:
                row["precision"] = (
                    row["correct"] / row["guessed"] if row["guessed"] else None
                )
            else:
                row.pop("correct", None)
    return {
        "by_basis": dict(sorted(by_basis.items())),
        "by_confidence_band": dict(sorted(by_band.items())),
    }


def _section_summary(
    selected: int, results_by_id: dict[str, dict[str, Any]], *, validation: bool
) -> dict[str, Any]:
    results = list(results_by_id.values())
    statuses = Counter(str(result.get("status") or "missing") for result in results)
    guessed = statuses["guessed"]
    guessed_rows = list(_guesses(results))
    lower_bounds = sum(
        result["guess"].get("basis") == "latest data year (lower bound)"
        for result in guessed_rows
    )
    date_guesses = guessed - lower_bounds
    out: dict[str, Any] = {
        "selected": selected,
        "attempted": len(results),
        "guessed": guessed,
        "abstained": statuses["abstained"],
        "no_ocr": statuses["no_ocr"],
        "empty_ocr": statuses["empty_ocr"],
        "invalid": statuses["invalid"],
        "errors": statuses["error"],
        "recovery_coverage": guessed / selected if selected else None,
        "date_guesses": date_guesses,
        "lower_bound_estimates": lower_bounds,
        "date_guess_coverage": date_guesses / selected if selected else None,
    }
    if validation:
        correct = sum(result.get("correct") is True for result in results)
        incorrect = sum(result.get("correct") is False for result in results)
        within_one = sum(
            isinstance(result.get("expected_year"), int)
            and isinstance(result.get("guess", {}).get("year"), int)
            and abs(result["expected_year"] - result["guess"]["year"]) <= 1
            for result in guessed_rows
        )
        date_correct = sum(
            result.get("correct") is True
            and result.get("guess", {}).get("basis")
            != "latest data year (lower bound)"
            for result in guessed_rows
        )
        lower_bound_correct = sum(
            result.get("correct") is True
            and result.get("guess", {}).get("basis")
            == "latest data year (lower bound)"
            for result in guessed_rows
        )
        date_within_one = sum(
            result.get("guess", {}).get("basis")
            != "latest data year (lower bound)"
            and isinstance(result.get("expected_year"), int)
            and isinstance(result.get("guess", {}).get("year"), int)
            and abs(result["expected_year"] - result["guess"]["year"]) <= 1
            for result in guessed_rows
        )
        out.update(
            {
                "correct": correct,
                "incorrect": incorrect,
                "exact_precision": correct / guessed if guessed else None,
                "within_one_year": within_one,
                "within_one_year_rate": within_one / guessed if guessed else None,
                "exact_yield": correct / selected if selected else None,
                "date_guess_correct": date_correct,
                "date_guess_exact_precision": (
                    date_correct / date_guesses if date_guesses else None
                ),
                "date_guess_within_one_year": date_within_one,
                "date_guess_within_one_year_rate": (
                    date_within_one / date_guesses if date_guesses else None
                ),
                "lower_bound_exact_matches": lower_bound_correct,
            }
        )
    out.update(_breakdown(results, validation=validation))
    return out


def _summarize(state: dict[str, Any]) -> dict[str, Any]:
    selected = state["selected"]
    results = state["results"]
    return {
        "validation": _section_summary(
            len(selected["validation"]), results["validation"], validation=True
        ),
        "unknown": _section_summary(
            len(selected["unknown"]), results["unknown"], validation=False
        ),
    }


def _checkpoint(path: Path, state: dict[str, Any]) -> None:
    state["summary"] = _summarize(state)
    _atomic_json(path, state)


def _process(
    state: dict[str, Any],
    *,
    archive: Any,
    infer_text: Callable[[dict[str, Any], str], Any],
    delay_seconds: float,
    checkpoint_every: int,
    out_path: Path,
) -> None:
    delay = _PoliteDelay(delay_seconds)
    since_checkpoint = 0
    attempted_this_run = 0

    # Validation comes first because coverage is not trustworthy until the
    # held-out answers say how often a recovered year is actually right.
    work: list[tuple[str, dict[str, Any], int | None]] = []
    for selected in state["selected"]["validation"]:
        work.append(("validation", selected["item"], int(selected["expected_year"])))
    for item in state["selected"]["unknown"]:
        work.append(("unknown", item, None))

    total = len(work)
    for position, (section, item, expected) in enumerate(work, 1):
        identifier = str(item.get("identifier") or "")
        old = state["results"][section].get(identifier)
        if _completed(old):
            continue

        result = _one_result(archive, item, infer_text, delay)
        if expected is not None:
            result["expected_year"] = expected
            if result.get("status") == "guessed":
                result["correct"] = result["guess"].get("year") == expected
        state["results"][section][identifier] = result
        since_checkpoint += 1
        attempted_this_run += 1

        if since_checkpoint >= checkpoint_every:
            _checkpoint(out_path, state)
            since_checkpoint = 0
        if attempted_this_run % 25 == 0 or position == total:
            print(
                f"  {position}/{total} selected; {attempted_this_run} attempted this run",
                flush=True,
            )

    _checkpoint(out_path, state)


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _print_rows(rows: dict[str, dict[str, Any]], *, validation: bool) -> None:
    if not rows:
        print("    (none)")
        return
    for label, row in rows.items():
        suffix = (
            f", {row['correct']}/{row['guessed']} correct "
            f"({_percent(row.get('precision'))})"
            if validation
            else ""
        )
        print(f"    {label}: {row['guessed']} recovered{suffix}")


def _print_summary(state: dict[str, Any], out_path: Path) -> None:
    summary = state["summary"]
    validation = summary["validation"]
    unknown = summary["unknown"]

    print("\nVALIDATION — HELD-OUT CATALOGUE YEARS")
    print(
        "  exact precision  : "
        f"{_percent(validation['exact_precision'])} "
        f"({validation['correct']}/{validation['guessed']} recovered guesses correct)"
    )
    print(
        "  date-guess precision: "
        f"{_percent(validation['date_guess_exact_precision'])} "
        f"({validation['date_guess_correct']}/{validation['date_guesses']} "
        "non-lower-bound guesses correct)"
    )
    print(
        "  date guesses within ±1 year (secondary): "
        f"{_percent(validation['date_guess_within_one_year_rate'])} "
        f"({validation['date_guess_within_one_year']}/"
        f"{validation['date_guesses']})"
    )
    print(
        "  recovery coverage: "
        f"{_percent(validation['recovery_coverage'])} "
        f"({validation['guessed']}/{validation['selected']} selected items)"
    )
    print(
        "  exact yield       : "
        f"{_percent(validation['exact_yield'])} "
        f"({validation['correct']}/{validation['selected']} selected items correct)"
    )
    print(
        "  lower-bound estimates: "
        f"{validation['lower_bound_estimates']} "
        f"({validation['lower_bound_exact_matches']} happened to equal the "
        "catalogue year; these are not exact-date claims)"
    )
    print(
        "  residue           : "
        f"{validation['abstained']} abstained, {validation['no_ocr']} no OCR, "
        f"{validation['empty_ocr']} empty OCR, {validation['invalid']} invalid, "
        f"{validation['errors']} errors"
    )
    print("  by basis:")
    _print_rows(validation["by_basis"], validation=True)
    print("  by confidence band:")
    _print_rows(validation["by_confidence_band"], validation=True)

    print("\nYEAR-LESS REPAIR RESIDUE")
    print(
        f"  proposed dates      : {unknown['date_guesses']}/{unknown['selected']} "
        f"({_percent(unknown['date_guess_coverage'])})"
    )
    print(
        f"  including bounds    : {unknown['guessed']}/{unknown['selected']} "
        f"({_percent(unknown['recovery_coverage'])})"
    )
    print(f"  lower-bound estimates: {unknown['lower_bound_estimates']}")
    print(
        "  residue            : "
        f"{unknown['abstained']} abstained, {unknown['no_ocr']} no OCR, "
        f"{unknown['empty_ocr']} empty OCR, {unknown['invalid']} invalid, "
        f"{unknown['errors']} errors"
    )
    print("  by basis:")
    _print_rows(unknown["by_basis"], validation=False)
    print("  by confidence band:")
    _print_rows(unknown["by_confidence_band"], validation=False)
    print(f"\ncheckpoint and full evidence: {out_path}")


def main(argv: list[str] | None = None) -> int:
    ap = _parser()
    args = ap.parse_args(argv)
    if args.unknown_sample < 0 or args.validation_sample < 0:
        ap.error("sample sizes must be non-negative")
    if args.sleep < 0:
        ap.error("--sleep must be non-negative")
    if args.checkpoint_every < 1:
        ap.error("--checkpoint-every must be at least 1")

    # Delayed until after argument parsing so `--help` never initializes the
    # archive or requires a partially installed checkout.
    from groundtruth.archive import Archive
    from groundtruth.dating import infer_year_from_text
    from groundtruth.repair import infer_year

    out_path = Path(args.out)
    archive = Archive(cache_dir=args.cache_dir)

    try:
        if out_path.exists() and not args.fresh:
            state = _load_state(out_path)
            _check_resume(state, args)
            print(
                f"resuming {out_path} with "
                f"{len(state['results']['unknown'])} unknown and "
                f"{len(state['results']['validation'])} validation results",
                flush=True,
            )
        else:
            index = archive.load_index()
            state = _new_state(
                index,
                unknown_n=args.unknown_sample,
                validation_n=args.validation_sample,
                seed=args.seed,
                validation_seed=args.validation_seed,
                collection=archive.collection,
                metadata_infer=infer_year,
            )
            _checkpoint(out_path, state)
            pop = state["population"]
            print(
                f"froze {args.unknown_sample} of {pop['repair_residual_items']:,} "
                "year-less residual items and "
                f"{args.validation_sample} of {pop['validation_evaluation_items']:,} "
                "calibration-disjoint validation items",
                flush=True,
            )

        _process(
            state,
            archive=archive,
            infer_text=infer_year_from_text,
            delay_seconds=args.sleep,
            checkpoint_every=args.checkpoint_every,
            out_path=out_path,
        )
    except KeyboardInterrupt:
        if "state" in locals():
            _checkpoint(out_path, state)
            print(f"\ninterrupted; checkpoint preserved at {out_path}", file=sys.stderr)
        return 130
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"recover_years: {exc}", file=sys.stderr)
        return 2

    _print_summary(state, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
