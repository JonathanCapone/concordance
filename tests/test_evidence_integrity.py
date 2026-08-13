"""Evidence syntax and incoming record shape are part of the trust boundary."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from concordance.contribute import (
    Verdict,
    _match_evidence_span,
    _value_in_quote,
    make_bundle,
    merge_bundle,
    public_record_key,
    verify_bundle,
)
from concordance.disputes import Claim, check, load_claims, submit
from concordance.tools import Corpus


class Archive:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def pages(self, identifier: str):
        self.calls += 1
        text = self.text

        class Page:
            page = 1

            def __init__(self) -> None:
                self.text = text

        return [Page()]


def record(
    value: float | None,
    quote: str,
    *,
    parameter: str = "BOD",
    kind: str = "observation",
    path: str = "prose",
) -> dict:
    return {
        "kind": kind,
        "parameter": parameter,
        "value": value,
        "unit": None if kind == "conclusion" else "mg/L",
        "stream": "effluent",
        "place": "Example",
        "period": "1969",
        "confidence": 0.9,
        "raw": {},
        "provenance": {
            "identifier": "item",
            "page": 1,
            "source_text": quote,
            "path": path,
        },
    }


@pytest.mark.parametrize(
    ("page_number", "invented_number"),
    [("312", "3.12"), ("123", "1.23"), ("10", "1.0")],
)
def test_decimal_insertion_cannot_turn_page_digits_into_a_new_number(
    page_number: str, invented_number: str,
) -> None:
    page = f"The BOD result was {page_number} mg/L."
    quote = f"The BOD result was {invented_number} mg/L."
    value = float(invented_number)

    assert _match_evidence_span(quote, page) is None
    verdict = verify_bundle(make_bundle([record(value, quote)]), archive=Archive(page))
    assert verdict.verified == 0
    assert verdict.supported == []
    assert "not on that page" in verdict.failed[0]["why"]


@pytest.mark.parametrize(
    ("page", "quote"),
    [
        ("The BOD result was > 5 mg/L.", "The BOD result was < 5 mg/L."),
        ("The BOD result was -5 mg/L.", "The BOD result was 5 mg/L."),
        ("The BOD result was ±5 mg/L.", "The BOD result was 5 mg/L."),
    ],
)
def test_semantic_signs_cannot_be_inserted_removed_or_reversed(page: str, quote: str) -> None:
    assert _match_evidence_span(quote, page) is None


def test_legitimate_ocr_spacing_thousands_and_scale_still_verify() -> None:
    page = (
        "The daily flow was 3. 0 million gallons and the operating cost was "
        "$53, 549. 66."
    )
    assert _match_evidence_span(
        "The daily flow was 3.0 million gallons", page,
    ) == "The daily flow was 3. 0 million gallons"
    assert _value_in_quote(3_000_000, page)[0] == "ok"
    assert _value_in_quote(53_549.66, page)[0] == "ok"


def test_supported_prose_persists_the_page_characters_not_the_tidy_quote() -> None:
    page = "The daily flow was 8. 8 million gallons."
    quote = "The daily flow was 8.8 million gallons."
    verdict = verify_bundle(make_bundle([record(8.8, quote)]), archive=Archive(page))
    assert verdict.verified == 1
    supported_quote = verdict.supported[0]["provenance"]["source_text"]
    assert supported_quote == page


def test_a_naked_number_is_not_a_prose_source_sentence() -> None:
    page = "The plant's total operating cost was 41.2 dollars."
    offered = record(41.2, "41.2", parameter="mercury")
    verdict = verify_bundle(make_bundle([offered]), archive=Archive(page))
    assert verdict.verified == 0
    assert verdict.supported == []
    assert "textual context" in verdict.failed[0]["why"]


@pytest.mark.parametrize("fabricated", [5, 53, 549, 9])
def test_table_values_are_complete_tokens_not_whole_page_digit_substrings(
    fabricated: float,
) -> None:
    page = "January BOD total operating cost 53,549.66"
    offered = record(
        fabricated,
        "table cell [January / BOD]",
        path="vision",
    )
    standing = check(Claim(record=offered), pages={"item": {1: page}})
    assert not standing.verified
    assert "localized cell evidence" in standing.why


def test_invented_table_headings_plus_an_unrelated_real_number_do_not_verify() -> None:
    page = "STATEMENT No. 4 Continued. SUMMIT WATER SUPPLY. 41.2"
    offered = record(
        41.2,
        "table cell [Completely Invented Row / Completely Invented Column]",
        path="vision",
    )
    verdict = verify_bundle(make_bundle([offered]), archive=Archive(page))
    assert verdict.verified == 0
    assert verdict.supported == []
    assert verdict.failed


@pytest.mark.parametrize(
    "quote",
    [
        "table cell [FLOW Completely Invented Row / FLOW Completely Invented Column]",
        "table cell [FLOW / FLOW]",
    ],
)
def test_common_or_repeated_heading_tokens_cannot_fake_a_table_locator(quote: str) -> None:
    page = "TABLE: FLOW. The unrelated total was 41.2."
    offered = record(41.2, quote, path="vision")

    standing = check(Claim(record=offered), pages={"item": {1: page}})
    verdict = verify_bundle(make_bundle([offered]), archive=Archive(page))

    assert not standing.verified
    assert verdict.verified == 0
    assert verdict.supported == []


def test_real_table_headings_cannot_launder_a_value_from_the_wrong_row() -> None:
    page = "FLOW\nJanuary 41.2\nFebruary 99.0"
    offered = record(
        41.2,
        "table cell [February / FLOW]",
        path="vision",
    )

    standing = check(Claim(record=offered), pages={"item": {1: page}})
    verdict = verify_bundle(make_bundle([offered]), archive=Archive(page))

    assert not standing.verified
    assert "localized cell evidence" in standing.why
    assert verdict.verified == 0
    assert verdict.supported == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(kind="invented"),
        lambda r: r.update(parameter=""),
        lambda r: r.update(value=None),
        lambda r: r.update(value=True),
        lambda r: r.update(value=float("nan")),
        lambda r: r.update(confidence="certain"),
        lambda r: r.update(stream="outlet-ish"),
        lambda r: r.update(raw=[]),
        lambda r: r.update(provenance=[]),
    ],
)
def test_invalid_record_shapes_fail_before_archive_work(mutate) -> None:
    offered = record(5.0, "The BOD result was 5 mg/L.")
    mutate(offered)
    archive = Archive("The BOD result was 5 mg/L.")
    verdict = verify_bundle(make_bundle([offered]), archive=archive)
    assert verdict.failed
    assert verdict.supported == []
    assert archive.calls == 0


def test_only_a_valid_conclusion_may_omit_a_number() -> None:
    quote = "No guideline was exceeded."
    offered = record(None, quote, kind="conclusion", parameter="assessment")
    verdict = verify_bundle(make_bundle([offered]), archive=Archive(quote))
    assert not verdict.failed
    assert len(verdict.unchecked) == 1
    assert verdict.supported == [offered]


def test_one_valid_record_cannot_carry_blank_observations() -> None:
    quote = "The BOD result was 5 mg/L."
    good = record(5.0, quote)
    blank = record(None, quote, parameter="")
    verdict = verify_bundle(make_bundle([good, blank]), archive=Archive(quote))
    assert verdict.accepted is False
    assert verdict.verified == 1
    assert verdict.supported == [good]
    assert len(verdict.failed) == 1


def test_merge_revalidates_even_a_hand_built_verdict(tmp_path) -> None:
    invalid = record(None, "The BOD result was 5 mg/L.")
    verdict = Verdict(total=1, verified=1, supported=[invalid])
    with pytest.raises(ValueError, match="invalid"):
        merge_bundle(make_bundle([invalid]), into=tmp_path, verdict=verdict)
    assert list(tmp_path.iterdir()) == []


def test_renamed_report_records_are_not_loaded_as_public_claims(tmp_path) -> None:
    example = record(5.0, "The BOD result was 5 mg/L.")
    (tmp_path / "gold_report.before-prompt-widening.json").write_text(
        json.dumps({"records": [example]}), encoding="utf-8",
    )
    assert load_claims(tmp_path) == []


def test_report_records_do_not_suppress_a_legitimate_merge(tmp_path) -> None:
    example = record(5.0, "The BOD result was 5 mg/L.")
    (tmp_path / "renamed-benchmark.json").write_text(
        json.dumps({"records": [example]}), encoding="utf-8",
    )
    verdict = Verdict(total=1, verified=1, supported=[example])
    outcome = merge_bundle(make_bundle([example]), into=tmp_path, verdict=verdict)
    assert outcome["accepted"] == 1
    assert len(Corpus.load_dir(tmp_path).records) == 1


@pytest.mark.parametrize(("stored", "incoming"), [(1, 1.0), (0, -0.0)])
def test_public_identity_canonicalizes_equivalent_numeric_json_forms(
    tmp_path, stored, incoming,
) -> None:
    existing = record(stored, f"The BOD result was {stored} mg/L.")
    offered = dict(existing, value=incoming)
    assert public_record_key(existing) == public_record_key(offered)
    assert make_bundle([existing])["bundle_id"] == make_bundle([offered])["bundle_id"]

    (tmp_path / "example.json").write_text(
        json.dumps({"place": "Example", "records": [existing]}), encoding="utf-8",
    )
    verdict = Verdict(total=1, verified=1, supported=[offered])
    outcome = merge_bundle(make_bundle([offered]), into=tmp_path, verdict=verdict)
    assert outcome["accepted"] == 0
    assert outcome["duplicates_dropped"] == 1


def test_replayed_concurrent_individual_submission_is_create_once(tmp_path) -> None:
    quote = "The BOD result was 5 mg/L."
    offered = record(5.0, quote)

    def send(_):
        return submit(offered.copy(), archive=Archive(quote), directory=tmp_path)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(send, range(2)))

    assert sorted(outcome.stored for outcome in outcomes) == [False, True]
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    stored = json.loads(files[0].read_text(encoding="utf-8"))
    assert stored["records"][0]["value"] == 5.0
