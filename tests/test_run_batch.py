"""Resume-safety tests for the unattended town runner.

An incremental municipality JSON is evidence of progress, not completion.  The
batch planner may skip it only when a clean run produced a receipt that still
matches the exact result and catalogue snapshot.
"""

from __future__ import annotations

import collections
import json
import os
import subprocess
from pathlib import Path

from scripts.run_batch import (
    completed_reports,
    has_completion_receipt,
    plan_batch,
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


def test_filename_without_completion_receipt_is_resumed_not_skipped(tmp_path):
    _result(tmp_path / "belleville.json", "Belleville")
    counts = collections.Counter({"Belleville": 10, "Coniston": 9})

    queue, skipped = plan_batch(counts, tmp_path, 2, skip_done=True)

    assert skipped == 0
    assert [(town.place, town.state) for town in queue] == [
        ("Belleville", "resume-unverified"),
        ("Coniston", "new"),
    ]


def test_matching_receipt_is_the_only_evidence_that_skips_a_town(tmp_path):
    _result(tmp_path / "belleville.json", "Belleville")
    write_completion_receipt(tmp_path, "Belleville", 10, 10)

    queue, skipped = plan_batch(
        collections.Counter({"Belleville": 10, "Coniston": 9}),
        tmp_path,
        2,
        skip_done=True,
    )

    assert skipped == 1
    assert [town.place for town in queue] == ["Coniston"]


def test_result_progress_after_receipt_invalidates_completion(tmp_path):
    result = tmp_path / "belleville.json"
    _result(result, "Belleville")
    write_completion_receipt(tmp_path, "Belleville", 10, 10)
    _result(result, "Belleville", pages=["item#1", "item#2"])

    assert not has_completion_receipt(tmp_path, "Belleville", 10)
    queue, _ = plan_batch(
        collections.Counter({"Belleville": 10}), tmp_path, 1, skip_done=True
    )
    assert queue[0].state == "resume-unverified"


def test_wrong_place_result_is_blocked_instead_of_overwritten(tmp_path):
    _result(tmp_path / "belleville.json", "A Different Municipality")

    queue, skipped = plan_batch(
        collections.Counter({"Belleville": 10}), tmp_path, 1, skip_done=True
    )

    assert skipped == 0
    assert queue[0].state == "blocked-invalid"


def test_catalogue_growth_invalidates_completion_receipt(tmp_path):
    _result(tmp_path / "belleville.json", "Belleville")
    write_completion_receipt(tmp_path, "Belleville", 10, 10)

    assert has_completion_receipt(tmp_path, "Belleville", 10)
    assert not has_completion_receipt(tmp_path, "Belleville", 11)


def test_no_skip_done_explicitly_requeues_a_verified_town(tmp_path):
    _result(tmp_path / "belleville.json", "Belleville")
    write_completion_receipt(tmp_path, "Belleville", 10, 10)

    queue, skipped = plan_batch(
        collections.Counter({"Belleville": 10}), tmp_path, 1, skip_done=False
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
    counts = collections.Counter({"Older": 12, "New": 11, "Interrupted": 10})

    queue, _ = plan_batch(counts, tmp_path, 3, skip_done=True)

    assert [town.place for town in queue] == ["Interrupted", "Older", "New"]


def test_clean_final_summary_is_required_for_completion():
    clean = subprocess.CompletedProcess(
        [], 0, "wrote data/results/a.json  --  12 records from 3 reports\n", ""
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

    assert completed_reports(clean) == 3
    assert completed_reports(failed_page) is None
    assert completed_reports(killed) is None
    assert completed_reports(no_summary) is None


def test_inconsistent_result_cannot_receive_a_receipt(tmp_path):
    result = tmp_path / "belleville.json"
    _result(result, "Belleville")
    payload = json.loads(result.read_text("utf-8"))
    payload["n_records"] = 99
    result.write_text(json.dumps(payload), encoding="utf-8")

    try:
        write_completion_receipt(tmp_path, "Belleville", 10, 10)
    except ValueError as exc:
        assert "internally inconsistent" in str(exc)
    else:
        raise AssertionError("an inconsistent partial result was marked complete")
