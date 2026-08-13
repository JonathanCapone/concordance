"""Resume-safety tests for the unattended town runner.

An incremental municipality JSON is evidence of progress, not completion.  The
batch planner may skip it only when a clean run produced a receipt that still
matches the exact result, extractor code, and ordered report selection.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from scripts.run_batch import (
    COMPLETION_SCHEMA,
    CompletionEvidence,
    completion_evidence,
    completion_path_for,
    extractor_fingerprint,
    has_completion_receipt,
    plan_batch,
    select_report_identifiers,
    selection_fingerprint,
    write_completion_receipt,
)


def _result(path: Path, place: str, *, pages: list[str] | None = None) -> None:
    records = [
        {
            "parameter": "flow",
            "value": 1,
            "provenance": {"identifier": "item", "page": 1},
        }
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "place": place,
                "model": "local-test-model",
                "n_records": len(records),
                "pages_attempted": pages or ["item#1"],
                "records": records,
            }
        ),
        encoding="utf-8",
    )


def _selection(place: str, reports: int) -> tuple[str, ...]:
    slug = place.lower().replace(" ", "-")
    return tuple(f"{slug}-report-{n}" for n in range(reports))


def test_filename_without_completion_receipt_is_resumed_not_skipped(tmp_path):
    _result(tmp_path / "belleville.json", "Belleville")
    selections = {
        "Belleville": _selection("Belleville", 10),
        "Coniston": _selection("Coniston", 9),
    }

    queue, skipped = plan_batch(selections, tmp_path, 2, skip_done=True)

    assert skipped == 0
    assert [(town.place, town.state) for town in queue] == [
        ("Belleville", "resume-unverified"),
        ("Coniston", "new"),
    ]


def test_matching_receipt_is_the_only_evidence_that_skips_a_town(tmp_path):
    _result(tmp_path / "belleville.json", "Belleville")
    selection = _selection("Belleville", 10)
    write_completion_receipt(
        tmp_path, "Belleville", selection, CompletionEvidence(1, selection)
    )

    queue, skipped = plan_batch(
        {"Belleville": selection, "Coniston": _selection("Coniston", 9)},
        tmp_path,
        2,
        skip_done=True,
    )

    assert skipped == 1
    assert [town.place for town in queue] == ["Coniston"]


def test_result_progress_after_receipt_invalidates_completion(tmp_path):
    result = tmp_path / "belleville.json"
    _result(result, "Belleville")
    selection = _selection("Belleville", 10)
    write_completion_receipt(
        tmp_path, "Belleville", selection, CompletionEvidence(1, selection)
    )
    _result(result, "Belleville", pages=["item#1", "item#2"])

    assert not has_completion_receipt(tmp_path, "Belleville", selection)
    queue, _ = plan_batch(
        {"Belleville": selection}, tmp_path, 1, skip_done=True
    )
    assert queue[0].state == "resume-unverified"


def test_wrong_place_result_is_blocked_instead_of_overwritten(tmp_path):
    _result(tmp_path / "belleville.json", "A Different Municipality")

    queue, skipped = plan_batch(
        {"Belleville": _selection("Belleville", 10)}, tmp_path, 1, skip_done=True
    )

    assert skipped == 0
    assert queue[0].state == "blocked-invalid"


def test_selection_membership_or_order_change_invalidates_completion_receipt(tmp_path):
    _result(tmp_path / "belleville.json", "Belleville")
    selection = _selection("Belleville", 3)
    write_completion_receipt(
        tmp_path, "Belleville", selection, CompletionEvidence(1, selection)
    )

    assert has_completion_receipt(tmp_path, "Belleville", selection)
    assert not has_completion_receipt(
        tmp_path, "Belleville", (selection[0], "new-report", selection[2])
    )
    assert not has_completion_receipt(tmp_path, "Belleville", tuple(reversed(selection)))


def test_selection_fingerprint_is_order_sensitive():
    assert selection_fingerprint(("a", "b")) != selection_fingerprint(("b", "a"))


def test_schema_one_receipt_is_invalidated(tmp_path):
    _result(tmp_path / "belleville.json", "Belleville")
    selection = _selection("Belleville", 3)
    write_completion_receipt(
        tmp_path, "Belleville", selection, CompletionEvidence(1, selection)
    )
    receipt_path = completion_path_for(tmp_path, "Belleville")
    receipt = json.loads(receipt_path.read_text("utf-8"))
    assert receipt["schema"] == COMPLETION_SCHEMA == 2
    receipt["schema"] = 1
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    assert not has_completion_receipt(tmp_path, "Belleville", selection)


def test_extractor_change_invalidates_completion_receipt(tmp_path):
    _result(tmp_path / "belleville.json", "Belleville")
    selection = _selection("Belleville", 3)
    write_completion_receipt(
        tmp_path,
        "Belleville",
        selection,
        CompletionEvidence(1, selection),
        extractor_sha256="extractor-before",
    )

    assert has_completion_receipt(
        tmp_path, "Belleville", selection, extractor_sha256="extractor-before"
    )
    assert not has_completion_receipt(
        tmp_path, "Belleville", selection, extractor_sha256="extractor-after"
    )


def test_extractor_fingerprint_covers_archive_selection_dependency(tmp_path):
    child = tmp_path / "extract_place.py"
    archive = tmp_path / "archive.py"
    child.write_text("child-v1", encoding="utf-8")
    archive.write_text("archive-v1", encoding="utf-8")
    before = extractor_fingerprint((child, archive))
    archive.write_text("archive-v2", encoding="utf-8")

    assert extractor_fingerprint((child, archive)) != before


def test_no_skip_done_explicitly_requeues_a_verified_town(tmp_path):
    _result(tmp_path / "belleville.json", "Belleville")
    selection = _selection("Belleville", 10)
    write_completion_receipt(
        tmp_path, "Belleville", selection, CompletionEvidence(1, selection)
    )

    queue, skipped = plan_batch(
        {"Belleville": selection}, tmp_path, 1, skip_done=False
    )

    assert skipped == 0
    assert [(town.place, town.state) for town in queue] == [
        ("Belleville", "complete")
    ]


def test_most_recent_unverified_result_resumes_before_legacy_and_new_towns(tmp_path):
    older = tmp_path / "older.json"
    interrupted = tmp_path / "interrupted.json"
    _result(older, "Older")
    _result(interrupted, "Interrupted")
    os.utime(older, ns=(1_000_000_000, 1_000_000_000))
    os.utime(interrupted, ns=(2_000_000_000, 2_000_000_000))
    selections = {
        "Older": _selection("Older", 12),
        "New": _selection("New", 11),
        "Interrupted": _selection("Interrupted", 10),
    }

    queue, _ = plan_batch(selections, tmp_path, 3, skip_done=True)

    assert [town.place for town in queue] == ["Interrupted", "Older", "New"]


def test_clean_final_summary_and_exact_item_lines_are_required_for_completion():
    clean = subprocess.CompletedProcess(
        [],
        0,
        "  report-a 1961: 20 pages, 3 prose\n"
        "  report-b 1962: 21 pages, 4 prose\n"
        "  report-c 1963: 22 pages, 5 prose\n"
        "wrote data/results/a.json  --  12 records from 3 reports\n",
        "",
    )
    failed_page = subprocess.CompletedProcess(
        [],
        0,
        "item 1969: FAILED to load pages (temporary error)\n"
        "wrote data/results/a.json  --  12 records from 3 reports\n",
        "",
    )
    killed = subprocess.CompletedProcess([], 1, "", "killed")
    no_summary = subprocess.CompletedProcess([], 0, "12 records so far", "")

    assert completion_evidence(clean) == CompletionEvidence(
        12, ("report-a", "report-b", "report-c")
    )
    assert completion_evidence(failed_page) is None
    assert completion_evidence(killed) is None
    assert completion_evidence(no_summary) is None


def test_summary_count_without_all_report_identifiers_is_not_completion():
    missing_identifier = subprocess.CompletedProcess(
        [],
        0,
        "  report-a 1961: 20 pages, 3 prose\n"
        "wrote data/results/a.json  --  12 records from 3 reports\n",
        "",
    )

    assert completion_evidence(missing_identifier) is None


def test_child_selection_must_match_planned_identifiers_and_order(tmp_path):
    _result(tmp_path / "belleville.json", "Belleville")
    planned = _selection("Belleville", 10)
    only_three = planned[:3]

    try:
        write_completion_receipt(
            tmp_path, "Belleville", planned, CompletionEvidence(1, only_three)
        )
    except ValueError as exc:
        assert "ordered selection" in str(exc)
    else:
        raise AssertionError("3 child reports were accepted for a planned selection of 10")

    assert not completion_path_for(tmp_path, "Belleville").exists()


def test_report_selection_matches_extract_place_rules_exactly():
    items = [
        {"identifier": "later", "year": 1970, "title": "Belleville annual report"},
        {"identifier": "wrong-place", "year": 1950, "title": "Coniston annual report"},
        {"identifier": "not-annual", "year": 1955, "title": "Belleville special study"},
        {
            "identifier": "sewage",
            "year": 1960,
            "title": "Belleville sewage treatment plant operating summary",
        },
        {"identifier": "earlier", "year": 1961, "title": "BELLEVILLE annual report"},
    ]

    assert select_report_identifiers(items, "Belleville") == (
        "sewage",
        "earlier",
        "later",
    )
    assert select_report_identifiers(items, "Belleville", max_items=2) == (
        "sewage",
        "earlier",
    )


def test_inconsistent_result_cannot_receive_a_receipt(tmp_path):
    result = tmp_path / "belleville.json"
    _result(result, "Belleville")
    payload = json.loads(result.read_text("utf-8"))
    payload["n_records"] = 99
    result.write_text(json.dumps(payload), encoding="utf-8")

    try:
        selection = _selection("Belleville", 10)
        write_completion_receipt(
            tmp_path, "Belleville", selection, CompletionEvidence(1, selection)
        )
    except ValueError as exc:
        assert "internally inconsistent" in str(exc)
    else:
        raise AssertionError("an inconsistent partial result was marked complete")
