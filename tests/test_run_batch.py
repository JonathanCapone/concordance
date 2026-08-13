"""Resume-safety tests for the unattended town runner.

An incremental municipality JSON is evidence of progress, not completion.  The
batch planner may skip it only when a clean run produced a receipt that still
matches the exact result and ordered report selection.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.run_batch import (
    BatchRunActiveError,
    COMPLETION_SCHEMA,
    LEGACY_PASS_SCHEMA,
    CompletionEvidence,
    batch_lease_path,
    batch_run_lease,
    completion_evidence,
    completion_path_for,
    extraction_command,
    has_completion_receipt,
    has_legacy_pass_checkpoint,
    legacy_pass_path_for,
    managed_run_path_for,
    plan_batch,
    prepare_managed_run,
    result_path_for,
    select_report_identifiers,
    selection_fingerprint,
    slug_of,
    write_completion_receipt,
    write_legacy_pass_checkpoint,
)


def _result(
    path: Path,
    place: str,
    *,
    pages: list[str] | None = None,
    identifier: str | None = None,
) -> None:
    ident = identifier or f"{place.lower().replace(' ', '-')}-report-0"
    records = [
        {
            "parameter": "flow",
            "value": 1,
            "provenance": {"identifier": ident, "page": 1},
        }
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "place": place,
                "model": "local-test-model",
                "n_records": len(records),
                "pages_attempted": pages or [f"{ident}#1"],
                "records": records,
            }
        ),
        encoding="utf-8",
    )


def _selection(place: str, reports: int) -> tuple[str, ...]:
    slug = place.lower().replace(" ", "-")
    return tuple(f"{slug}-report-{n}" for n in range(reports))


def _evidence(n_records: int, identifiers: tuple[str, ...]) -> CompletionEvidence:
    return CompletionEvidence(
        n_records,
        identifiers,
        tuple(1 for _identifier in identifiers),
    )


def test_process_lease_is_exclusive_and_separate_from_result_provenance(tmp_path):
    results_dir = tmp_path / "data" / "results"

    with batch_run_lease(results_dir) as lease_path:
        assert lease_path == batch_lease_path(results_dir)
        assert results_dir not in lease_path.parents
        assert not results_dir.exists()
        with pytest.raises(BatchRunActiveError, match="no town was started"):
            with batch_run_lease(results_dir):
                pytest.fail("a second owner acquired the same batch lease")

    with batch_run_lease(results_dir):
        pass


def test_main_fails_before_archive_or_result_access_when_another_process_owns_lease(
    tmp_path,
):
    script = Path(__file__).resolve().parents[1] / "scripts" / "run_batch.py"
    results_dir = tmp_path / "data" / "results"

    with batch_run_lease(results_dir):
        proc = subprocess.run(
            [sys.executable, str(script), "--towns", "1"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=15,
        )

    assert proc.returncode == 2
    assert "another run_batch process already owns" in proc.stderr
    assert "no town was started" in proc.stderr
    assert not results_dir.exists()


def test_process_crash_releases_lease_and_stale_file_is_recoverable(tmp_path):
    code = """
import os
import sys
import time
from pathlib import Path
from scripts.run_batch import batch_run_lease

with batch_run_lease(Path(sys.argv[1])):
    print('LEASED', flush=True)
    time.sleep(60)
os._exit(9)
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", code, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "LEASED"
        with pytest.raises(BatchRunActiveError):
            with batch_run_lease(tmp_path):
                pytest.fail("the live child lease was ignored")
    finally:
        proc.kill()
        proc.wait(timeout=15)

    assert batch_lease_path(tmp_path).exists()
    with batch_run_lease(tmp_path):
        pass


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


@pytest.mark.parametrize(
    "place",
    [
        "Simcoe, County Of Norfolk : Municipal",
        "Haileybury : Water Treatment Plant And",
        "A/B",
        r"A\B",
        ".",
        "..",
        "../Belleville",
        r"..\Belleville",
        "CON",
        "con.txt",
        "NUL ",
        "LPT1",
        "AUX.",
        "trailing. ",
    ],
)
def test_batch_slug_and_all_derived_paths_are_windows_safe_and_contained(
    tmp_path, place,
):
    slug = slug_of(place)

    assert slug == slug_of(place)
    assert re.fullmatch(r"[a-z0-9-]+", slug)
    assert slug.split(".", 1)[0].casefold() not in {
        "con", "prn", "aux", "nul", "com1", "lpt1",
    }
    root = tmp_path.resolve()
    paths = [
        result_path_for(tmp_path, place),
        completion_path_for(tmp_path, place),
        managed_run_path_for(tmp_path, place),
        legacy_pass_path_for(tmp_path, place),
    ]
    assert len({path.name for path in paths}) == 1
    for path in paths:
        path.resolve().relative_to(root)
        assert path.name == f"{slug}.json"


def test_ordinary_place_slugs_remain_compatible():
    assert slug_of("Belleville") == "belleville"
    assert slug_of("Owen Sound") == "owen-sound"
    assert slug_of("Niagara-On-The-Lake") == "niagara-on-the-lake"
    assert slug_of("Sault Ste. Marie") == "sault-ste.-marie"
    assert slug_of("Moore Twp. - Corunna") == "moore-twp.---corunna"


def test_punctuation_that_used_to_collapse_cannot_collide():
    assert slug_of("A/B") != slug_of(r"A\B")
    assert slug_of("A:B") != slug_of("A?B")


def test_child_is_explicitly_given_the_same_safe_result_path(tmp_path):
    place = "Simcoe, County Of Norfolk : Municipal"
    queue, _ = plan_batch(
        {place: ("simcoe-report",)}, tmp_path, 1, skip_done=True,
    )

    command = extraction_command(queue[0], "test-model", 12.5)

    out_index = command.index("--out") + 1
    assert Path(command[out_index]) == result_path_for(tmp_path, place)
    assert ":" not in Path(command[out_index]).name


def test_planner_rejects_any_slug_collision_instead_of_sharing_a_file(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr("scripts.run_batch.slug_of", lambda _place: "same")

    with pytest.raises(ValueError, match="map to the same batch slug"):
        plan_batch(
            {"First": ("first-report",), "Second": ("second-report",)},
            tmp_path,
            2,
            skip_done=True,
        )


def test_every_derived_path_fails_closed_if_a_slug_tries_to_escape(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr("scripts.run_batch.slug_of", lambda _place: "../../escape")

    for builder in (
        result_path_for,
        completion_path_for,
        managed_run_path_for,
        legacy_pass_path_for,
    ):
        with pytest.raises(ValueError, match="escapes results directory"):
            builder(tmp_path, "Place")


def test_legacy_progress_cannot_become_receipt_managed_retroactively(tmp_path):
    _result(tmp_path / "belleville.json", "Belleville")

    assert not prepare_managed_run(
        tmp_path, "Belleville", _selection("Belleville", 3),
    )


def test_clean_legacy_pass_settles_scheduling_without_issuing_a_receipt(tmp_path):
    result = result_path_for(tmp_path, "Belleville")
    _result(result, "Belleville")
    selection = _selection("Belleville", 3)

    first_queue, first_skipped = plan_batch(
        {
            "Belleville": selection,
            "Coniston": _selection("Coniston", 2),
        },
        tmp_path,
        1,
        skip_done=True,
    )
    assert first_skipped == 0
    assert [(town.place, town.state) for town in first_queue] == [
        ("Belleville", "resume-unverified")
    ]

    snapshot = write_legacy_pass_checkpoint(
        tmp_path,
        "Belleville",
        selection,
        _evidence(1, selection),
    )
    assert snapshot.n_records == 1
    assert has_legacy_pass_checkpoint(tmp_path, "Belleville", selection)
    assert not has_completion_receipt(tmp_path, "Belleville", selection)
    assert not completion_path_for(tmp_path, "Belleville").exists()

    checkpoint = json.loads(
        legacy_pass_path_for(tmp_path, "Belleville").read_text("utf-8")
    )
    assert checkpoint["schema"] == LEGACY_PASS_SCHEMA
    assert checkpoint["status"] == "clean-incremental-pass-only"
    assert checkpoint["receipt_backed"] is False
    assert checkpoint["fresh_verification"] is False

    second_queue, second_skipped = plan_batch(
        {
            "Belleville": selection,
            "Coniston": _selection("Coniston", 2),
        },
        tmp_path,
        1,
        skip_done=True,
    )
    assert second_skipped == 1
    assert [(town.place, town.state) for town in second_queue] == [
        ("Coniston", "new")
    ]

    included_queue, included_skipped = plan_batch(
        {"Belleville": selection}, tmp_path, 1, skip_done=False,
    )
    assert included_skipped == 0
    assert [(town.place, town.state) for town in included_queue] == [
        ("Belleville", "legacy-pass-observed")
    ]


def test_legacy_pass_checkpoint_is_invalidated_by_result_or_selection_change(tmp_path):
    result = result_path_for(tmp_path, "Belleville")
    _result(result, "Belleville")
    selection = _selection("Belleville", 3)
    write_legacy_pass_checkpoint(
        tmp_path,
        "Belleville",
        selection,
        _evidence(1, selection),
    )

    assert not has_legacy_pass_checkpoint(
        tmp_path, "Belleville", tuple(reversed(selection))
    )
    _result(
        result,
        "Belleville",
        pages=["belleville-report-0#1", "belleville-report-0#2"],
    )
    assert not has_legacy_pass_checkpoint(tmp_path, "Belleville", selection)


def test_interrupted_managed_run_keeps_its_pre_result_marker(tmp_path):
    selection = _selection("Belleville", 3)

    assert prepare_managed_run(tmp_path, "Belleville", selection)
    _result(tmp_path / "belleville.json", "Belleville")
    assert prepare_managed_run(tmp_path, "Belleville", selection)
    assert not prepare_managed_run(
        tmp_path, "Belleville", tuple(reversed(selection)),
    )


def test_matching_receipt_is_the_only_evidence_that_skips_a_town(tmp_path):
    _result(tmp_path / "belleville.json", "Belleville")
    selection = _selection("Belleville", 10)
    write_completion_receipt(
        tmp_path, "Belleville", selection, _evidence(1, selection)
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
        tmp_path, "Belleville", selection, _evidence(1, selection)
    )
    _result(
        result,
        "Belleville",
        pages=["belleville-report-0#1", "belleville-report-0#2"],
    )

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


def test_result_with_record_outside_planned_selection_is_blocked(tmp_path):
    result = tmp_path / "belleville.json"
    _result(result, "Belleville", pages=["planned-report#1"])
    payload = json.loads(result.read_text("utf-8"))
    payload["records"][0]["provenance"] = {
        "identifier": "unrelated-report", "page": 1, "source_text": "x",
    }
    result.write_text(json.dumps(payload), encoding="utf-8")

    queue, skipped = plan_batch(
        {"Belleville": ("planned-report",)}, tmp_path, 1, skip_done=True,
    )

    assert skipped == 0
    assert queue[0].state == "blocked-invalid"


@pytest.mark.parametrize(
    "attempted",
    ["unrelated-report#1", "planned-report", "planned-report#zero", "#1"],
)
def test_untrusted_attempted_page_cannot_support_or_resume_receipt(
    tmp_path, attempted,
):
    result = tmp_path / "belleville.json"
    _result(result, "Belleville", pages=[attempted])
    payload = json.loads(result.read_text("utf-8"))
    payload["records"][0]["provenance"] = {
        "identifier": "planned-report", "page": 1, "source_text": "x",
    }
    result.write_text(json.dumps(payload), encoding="utf-8")

    queue, _ = plan_batch(
        {"Belleville": ("planned-report",)}, tmp_path, 1, skip_done=True,
    )

    assert queue[0].state == "blocked-invalid"


def test_selection_membership_or_order_change_invalidates_completion_receipt(tmp_path):
    _result(tmp_path / "belleville.json", "Belleville")
    selection = _selection("Belleville", 3)
    write_completion_receipt(
        tmp_path, "Belleville", selection, _evidence(1, selection)
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
        tmp_path, "Belleville", selection, _evidence(1, selection)
    )
    receipt_path = completion_path_for(tmp_path, "Belleville")
    receipt = json.loads(receipt_path.read_text("utf-8"))
    assert receipt["schema"] == COMPLETION_SCHEMA == 2
    receipt["schema"] = 1
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    assert not has_completion_receipt(tmp_path, "Belleville", selection)


def test_legacy_code_fingerprint_does_not_invalidate_selection_completion(tmp_path):
    _result(tmp_path / "belleville.json", "Belleville")
    selection = _selection("Belleville", 3)
    write_completion_receipt(
        tmp_path, "Belleville", selection, _evidence(1, selection)
    )
    receipt_path = completion_path_for(tmp_path, "Belleville")
    receipt = json.loads(receipt_path.read_text("utf-8"))
    assert "extractor_sha256" not in receipt
    # Early schema-2 receipts carried this field.  It was unsound provenance:
    # incremental extraction does not reread attempted pages when code changes.
    receipt["extractor_sha256"] = "stale-code-fingerprint"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    assert has_completion_receipt(tmp_path, "Belleville", selection)


def test_no_skip_done_help_is_explicitly_incremental_not_fresh_verification():
    script = Path(__file__).resolve().parents[1] / "scripts" / "run_batch.py"

    proc = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
        check=True,
    )

    help_text = " ".join(proc.stdout.split())
    assert "does not reread pages already attempted" in help_text
    assert "verify them again" not in help_text


def test_no_skip_done_includes_receipt_backed_town_without_claiming_reverification(
    tmp_path,
):
    _result(tmp_path / "belleville.json", "Belleville")
    selection = _selection("Belleville", 10)
    write_completion_receipt(
        tmp_path, "Belleville", selection, _evidence(1, selection)
    )

    queue, skipped = plan_batch(
        {"Belleville": selection}, tmp_path, 1, skip_done=False
    )

    assert skipped == 0
    assert [(town.place, town.state) for town in queue] == [
        ("Belleville", "receipt-backed")
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
        12, ("report-a", "report-b", "report-c"), (20, 21, 22)
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


def test_zero_page_report_summary_is_not_completion_evidence():
    zero_pages = subprocess.CompletedProcess(
        [],
        0,
        "  item1 1969: 0 pages, 0 prose\n"
        "wrote data/results/a.json  --  0 records from 1 reports\n",
        "",
    )

    assert completion_evidence(zero_pages) is None


def test_zero_page_evidence_cannot_be_written_as_a_receipt(tmp_path):
    result = result_path_for(tmp_path, "Belleville")
    result.write_text(
        json.dumps({
            "place": "Belleville",
            "model": "local-test-model",
            "n_records": 0,
            "pages_attempted": [],
            "records": [],
        }),
        encoding="utf-8",
    )
    evidence = CompletionEvidence(0, ("item1",), (0,))

    with pytest.raises(ValueError, match="zero-page"):
        write_completion_receipt(tmp_path, "Belleville", ("item1",), evidence)

    assert not completion_path_for(tmp_path, "Belleville").exists()


def test_child_selection_must_match_planned_identifiers_and_order(tmp_path):
    _result(tmp_path / "belleville.json", "Belleville")
    planned = _selection("Belleville", 10)
    only_three = planned[:3]

    try:
        write_completion_receipt(
            tmp_path, "Belleville", planned, _evidence(1, only_three)
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
            tmp_path, "Belleville", selection, _evidence(1, selection)
        )
    except ValueError as exc:
        assert "internally inconsistent" in str(exc)
    else:
        raise AssertionError("an inconsistent partial result was marked complete")
