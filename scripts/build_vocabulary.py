"""Build the provisional controlled vocabulary from frozen, checkable evidence.

The input is deliberately narrower than ``observed_terms.json``. That file is a
useful inventory, but it has no source quotes or units, so it cannot establish
that a name came from the archive or what kind of number it denotes. This builder
uses two evidence shapes that retain those controls:

* committed place-result records whose parameter is a complete token phrase in
  its own ``provenance.source_text``; and
* the stratified vocabulary report's archive-language terms, but only when one
  of its recorded spellings is a complete token phrase in its example quote.

By default inputs are read from ``git show HEAD:<path>``. This is important while
an extraction batch owns a working-tree result file: the build sees the last
frozen checkpoint and never reads or writes the live file. ``--worktree`` exists
for explicit, named inputs only.

Grouping is orthographic only. Case, punctuation and whitespace variants may be
aliases. No word or digit is removed, so ``population`` and ``design population``
or ``flow`` and ``total flow`` can never merge here. Every output term remains
``reviewed: false``. Existing parameter resolution is copied only when every
record-level occurrence agrees; uncertainty leaves both ``substance`` and
``measure`` empty.

Examples::

    python scripts/build_vocabulary.py --dry-run
    python scripts/build_vocabulary.py --output data/vocabulary/vocabulary.json
    python scripts/build_vocabulary.py --validate data/vocabulary/vocabulary.json
"""

from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from concordance.parameters import resolve as resolve_parameter  # noqa: E402
from concordance.vocab_sample import contradicted  # noqa: E402
from concordance.vocabulary import (  # noqa: E402
    Term,
    Vocabulary,
    load,
    normalise,
    save,
)

DEFAULT_OUTPUT = ROOT / "data" / "vocabulary" / "vocabulary.json"
RESULT_ROOT = "data/results"
STRATIFIED_REPORT = "data/results/vocab_coverage.stratified.json"
MEASUREMENT_KINDS = frozenset({"observation", "standard", "design"})


@dataclass
class BuildStats:
    source_label: str = ""
    extraction_sources: int = 0
    coverage_sources: int = 0
    skipped_sources: list[str] = field(default_factory=list)
    records_seen: int = 0
    records_attested: int = 0
    records_excluded_wrong_kind: int = 0
    records_excluded_unattested: int = 0
    coverage_terms_seen: int = 0
    coverage_terms_attested: int = 0
    evidence_readings: int = 0
    terms_built: int = 0
    terms_with_identity: int = 0
    terms_without_identity: int = 0


@dataclass
class _Group:
    spellings: collections.Counter[str] = field(default_factory=collections.Counter)
    units: collections.Counter[str] = field(default_factory=collections.Counter)
    readings: int = 0
    identity_pairs: set[tuple[str, str]] = field(default_factory=set)
    identity_uncertain: bool = False
    identity_observations: int = 0

    def add_name(self, name: str, count: int) -> None:
        spelling = " ".join(str(name).strip().split())
        if not spelling or count <= 0:
            return
        self.spellings[spelling] += count
        self.readings += count

    def add_unit(self, unit: Any, count: int = 1) -> None:
        text = " ".join(str(unit or "").strip().split())
        if text and count > 0:
            self.units[text] += count

    def observe_identity(self, name: str, unit: Any, source_text: str) -> None:
        self.identity_observations += 1
        resolved = resolve_parameter(name, unit, context=source_text)
        if resolved is None or contradicted(resolved.measure, unit):
            self.identity_uncertain = True
            return
        self.identity_pairs.add((resolved.substance, resolved.measure))


def is_attested(name: Any, source_text: Any) -> bool:
    """Whether ``name`` occurs as a complete normalized token phrase.

    The shared normalizer forgives orthography only. Padding both strings with a
    space supplies token boundaries, preventing a short name such as ``gas``
    from being "found" inside ``gasoline``.
    """
    key = normalise(str(name or ""))
    quote = normalise(str(source_text or ""))
    return bool(key and quote and f" {key} " in f" {quote} ")


def _is_extraction_payload(payload: Any) -> bool:
    """Recognize a place extraction, not any report that happens to have rows."""
    if not isinstance(payload, dict):
        return False
    required = {"place", "model", "n_records", "pages_attempted", "records"}
    if not required.issubset(payload):
        return False
    records = payload.get("records")
    n_records = payload.get("n_records")
    return (isinstance(records, list) and isinstance(n_records, int) and
            not isinstance(n_records, bool) and n_records == len(records))


def _is_coverage_payload(payload: Any) -> bool:
    if not isinstance(payload, dict) or not isinstance(payload.get("terms"), list):
        return False
    required = {"archive_language", "model_language", "controls", "stopping_rule"}
    return required.issubset(payload)


def _group_for(groups: dict[str, _Group], name: str) -> _Group | None:
    key = normalise(name)
    if not key:
        return None
    return groups.setdefault(key, _Group())


def _add_extraction(payload: dict[str, Any], groups: dict[str, _Group],
                    stats: BuildStats) -> None:
    stats.extraction_sources += 1
    for record in payload["records"]:
        stats.records_seen += 1
        if not isinstance(record, dict) or record.get("kind") not in MEASUREMENT_KINDS:
            stats.records_excluded_wrong_kind += 1
            continue
        name = " ".join(str(record.get("parameter") or "").strip().split())
        provenance = record.get("provenance") or {}
        quote = str(provenance.get("source_text") or "") if isinstance(provenance, dict) else ""
        if not is_attested(name, quote):
            stats.records_excluded_unattested += 1
            continue
        group = _group_for(groups, name)
        if group is None:
            stats.records_excluded_unattested += 1
            continue
        stats.records_attested += 1
        stats.evidence_readings += 1
        group.add_name(name, 1)
        group.add_unit(record.get("unit"))
        group.observe_identity(name, record.get("unit"), quote)


def _coverage_spelling(row: dict[str, Any]) -> str | None:
    """The one row spelling evidenced by its one retained example.

    ``written_as`` is frequency-ordered but the report does not retain a quote
    for each spelling. Accepting every variant would claim evidence that is no
    longer inspectable. The first spelling actually present in the retained
    example is the conservative usable subset.
    """
    quote = str(row.get("example") or "")
    candidates = list(row.get("written_as") or [])
    if row.get("term"):
        candidates.append(row["term"])
    for candidate in candidates:
        spelling = " ".join(str(candidate or "").strip().split())
        if is_attested(spelling, quote):
            return spelling
    return None


def _add_coverage(payload: dict[str, Any], groups: dict[str, _Group],
                  stats: BuildStats) -> None:
    stats.coverage_sources += 1
    for row in payload["terms"]:
        stats.coverage_terms_seen += 1
        if not isinstance(row, dict):
            continue
        if (not row.get("archive_language") or row.get("suspect_ocr") or
                int(row.get("verbatim_sightings") or 0) <= 0):
            continue
        spelling = _coverage_spelling(row)
        if not spelling:
            continue
        group = _group_for(groups, spelling)
        if group is None:
            continue
        count = int(row.get("verbatim_sightings") or 0)
        stats.coverage_terms_attested += 1
        stats.evidence_readings += count
        group.add_name(spelling, count)
        for unit_row in row.get("units") or []:
            if (isinstance(unit_row, (list, tuple)) and len(unit_row) == 2 and
                    isinstance(unit_row[1], int)):
                group.add_unit(unit_row[0], unit_row[1])
        # The aggregate report does not link each unit and spelling back to an
        # individual quote. It proves the name is archive language, not what the
        # name means, so it cannot contribute an automatic identity decision.


def _chosen_spelling(group: _Group) -> str:
    return min(group.spellings, key=lambda name: (
        -group.spellings[name], normalise(name), name.casefold(), name))


def _as_term(group: _Group) -> Term:
    chosen = _chosen_spelling(group)
    canonical = chosen.lower()
    aliases = tuple(sorted({name.lower() for name in group.spellings
                            if name.lower() != canonical},
                           key=lambda name: (normalise(name), name)))

    substance = measure = ""
    if (group.identity_observations > 0 and not group.identity_uncertain and
            len(group.identity_pairs) == 1):
        substance, measure = next(iter(group.identity_pairs))

    typical_units = tuple(unit for unit, _ in sorted(
        group.units.items(), key=lambda item: (-item[1], item[0].casefold(), item[0]))[:6])
    return Term(
        canonical=canonical,
        substance=substance,
        measure=measure,
        domain="",
        aliases=aliases,
        typical_units=typical_units,
        readings_covered=group.readings,
        reviewed=False,
    )


def build_vocabulary(
    sources: Iterable[tuple[str, Any]], *, source_label: str = ""
) -> tuple[Vocabulary, BuildStats]:
    """Build from already-decoded named payloads; useful to the CLI and tests."""
    groups: dict[str, _Group] = {}
    stats = BuildStats(source_label=source_label)
    for name, payload in sources:
        if _is_extraction_payload(payload):
            _add_extraction(payload, groups, stats)
        elif _is_coverage_payload(payload):
            _add_coverage(payload, groups, stats)
        else:
            stats.skipped_sources.append(name)

    terms = [_as_term(group) for _, group in sorted(groups.items()) if group.spellings]
    vocab = Vocabulary(terms=terms)
    vocab.require_valid()
    if any(term.reviewed for term in terms):
        raise ValueError("a generated term was incorrectly marked reviewed")

    stats.terms_built = len(terms)
    stats.terms_with_identity = sum(bool(term.substance and term.measure) for term in terms)
    stats.terms_without_identity = stats.terms_built - stats.terms_with_identity
    return vocab, stats


def _git(args: Sequence[str]) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=ROOT, check=False, capture_output=True, text=True,
        encoding="utf-8", errors="strict")
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def _git_paths(ref: str) -> list[str]:
    rows = _git(["ls-tree", "-r", "--name-only", ref, "--", RESULT_ROOT]).splitlines()
    return sorted(path for path in rows if path.endswith(".json"))


def _git_payload(ref: str, path: str) -> Any:
    return json.loads(_git(["show", f"{ref}:{path}"]))


def _safe_repo_path(raw: str) -> tuple[str, Path]:
    posix = PurePosixPath(str(raw).replace("\\", "/"))
    if posix.is_absolute() or ".." in posix.parts:
        raise ValueError(f"input must be a repository-relative path: {raw}")
    rel = posix.as_posix()
    resolved = (ROOT / Path(*posix.parts)).resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"input leaves the repository: {raw}") from exc
    return rel, resolved


def read_sources(*, git_ref: str = "HEAD", inputs: Sequence[str] = (),
                 worktree: bool = False) -> tuple[list[tuple[str, Any]], list[str]]:
    """Read named inputs and return payloads plus default-discovery skips."""
    if worktree and not inputs:
        raise ValueError("--worktree requires one or more explicit --input paths")

    explicit = bool(inputs)
    paths = [str(path) for path in inputs] if explicit else _git_paths(git_ref)
    sources: list[tuple[str, Any]] = []
    skipped: list[str] = []
    for raw in paths:
        rel, disk_path = _safe_repo_path(raw)
        payload = (json.loads(disk_path.read_text(encoding="utf-8")) if worktree
                   else _git_payload(git_ref, rel))
        supported = _is_extraction_payload(payload) or (
            _is_coverage_payload(payload) and (explicit or rel == STRATIFIED_REPORT))
        if not supported:
            if explicit:
                raise ValueError(f"unsupported vocabulary evidence shape: {rel}")
            skipped.append(rel)
            continue
        sources.append((rel, payload))
    return sources, skipped


def validate_output(path: str | Path) -> tuple[Vocabulary, dict[str, Any]]:
    """Validate both the JSON envelope and the vocabulary's matching invariants."""
    p = Path(path)
    payload = json.loads(p.read_text(encoding="utf-8"))
    errors: list[str] = []
    if not isinstance(payload, dict):
        raise ValueError("vocabulary output must be a JSON object")
    if type(payload.get("version")) is not int or payload.get("version") != 1:
        errors.append("version must be 1")
    if not isinstance(payload.get("note"), str):
        errors.append("note must be a string")
    rows = payload.get("terms")
    if not isinstance(rows, list):
        errors.append("terms must be a list")
        rows = []
    if (type(payload.get("n_terms")) is not int or
            payload.get("n_terms") != len(rows)):
        errors.append("n_terms does not equal the number of terms")

    text_fields = ("canonical", "substance", "measure", "domain")
    list_fields = ("aliases", "typical_units")
    required = set(text_fields + list_fields + ("readings_covered", "reviewed"))
    for index, row in enumerate(rows, 1):
        where = f"term row {index}"
        if not isinstance(row, dict):
            errors.append(f"{where} must be an object")
            continue
        missing = sorted(required - set(row))
        if missing:
            errors.append(f"{where} is missing: {', '.join(missing)}")
        for field_name in text_fields:
            if field_name in row and not isinstance(row[field_name], str):
                errors.append(f"{where}.{field_name} must be a string")
        for field_name in list_fields:
            value = row.get(field_name)
            if field_name in row and (not isinstance(value, list) or
                                      any(not isinstance(item, str) for item in value)):
                errors.append(f"{where}.{field_name} must be a list of strings")
        count = row.get("readings_covered")
        if ("readings_covered" in row and
                (isinstance(count, bool) or not isinstance(count, int))):
            errors.append(f"{where}.readings_covered must be an integer")
        if "reviewed" in row and not isinstance(row.get("reviewed"), bool):
            errors.append(f"{where}.reviewed must be true or false")

    load.cache_clear()
    # Only hand the loader a structurally typed payload. It is intentionally
    # forgiving for normal runtime use; a validation command must not let that
    # coercion turn the string "false" into the boolean true, for example.
    vocab = Vocabulary()
    if not errors:
        vocab = load(p)
        errors.extend(vocab.validation_errors())
        if len(vocab) != len(rows):
            errors.append("one or more term rows have no canonical name")
    if errors:
        raise ValueError("invalid vocabulary output:\n- " + "\n- ".join(errors))
    return vocab, payload


def _summary(stats: BuildStats) -> str:
    return json.dumps(asdict(stats), indent=2, ensure_ascii=False)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--git-ref", default="HEAD",
                        help="frozen Git revision to read (default: HEAD)")
    parser.add_argument("--input", action="append", default=[],
                        help="explicit repository-relative evidence path; repeatable")
    parser.add_argument("--worktree", action="store_true",
                        help="read explicit inputs from disk instead of a Git revision")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--dry-run", action="store_true",
                        help="build and validate in memory without writing")
    parser.add_argument("--validate", metavar="PATH",
                        help="validate an existing vocabulary and exit")
    args = parser.parse_args(argv)

    try:
        if args.validate:
            if args.input or args.worktree or args.dry_run:
                parser.error("--validate cannot be combined with build-source options")
            vocab, _ = validate_output(args.validate)
            reviewed = len(vocab) - len(vocab.unreviewed())
            print(f"valid: {len(vocab):,} terms; {reviewed:,} reviewed; "
                  f"{len(vocab.unreviewed()):,} unreviewed")
            return 0

        sources, discovery_skips = read_sources(
            git_ref=args.git_ref, inputs=args.input, worktree=args.worktree)
        if not sources:
            raise ValueError("no supported vocabulary evidence sources found")
        label = "worktree explicit inputs" if args.worktree else f"git {args.git_ref}"
        vocab, stats = build_vocabulary(sources, source_label=label)
        stats.skipped_sources.extend(discovery_skips)
        print(_summary(stats))

        if args.dry_run:
            print("dry run: vocabulary validated in memory; no file written")
            return 0

        note = (
            f"Provisional measurement names built from source-attested evidence in {label}. "
            "Grouping is orthographic only; unresolved or ambiguous identities are blank. "
            "Every entry remains reviewed=false until a person confirms its meaning."
        )
        output = save(vocab, args.output, note=note)
        written, _ = validate_output(output)
        if len(written) != len(vocab):
            raise ValueError("saved vocabulary did not round-trip at the same size")
        print(f"wrote and validated {len(written):,} terms -> {output}")
        return 0
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
