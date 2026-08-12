"""Deterministic publication-year inference from OCR text.

The dangerous failure mode here is a plausible wrong year, so these tests put
at least as much weight on abstention and verbatim evidence as on coverage.  All
fixtures are local OCR-like strings; the test suite must never contact the
Internet Archive.
"""

from __future__ import annotations

from argparse import Namespace
from copy import deepcopy

import pytest

from groundtruth.dating import DateGuess, infer_year_from_text
from groundtruth.models import PageText
from scripts.recover_years import (
    _PoliteDelay,
    _check_resume,
    _new_state,
    _one_result,
    _section_summary,
)


def _item(**changes):
    item = {"identifier": "dating-fixture", "title": "Undated report", "year": None}
    item.update(changes)
    return item


def _page(number: int, text: str, confidence: float | None = 0.9) -> PageText:
    return PageText(
        identifier="dating-fixture",
        page=number,
        text=text,
        ocr_confidence=confidence,
    )


def _assert_verbatim(guess: DateGuess, source: str | list[PageText]) -> None:
    assert guess.year is not None
    assert guess.evidence
    if isinstance(source, str):
        assert guess.evidence in source
    else:
        assert any(guess.evidence in page.text for page in source)


def _assert_abstains(guess: DateGuess) -> None:
    assert guess.year is None
    assert guess.confidence == 0.0
    assert guess.evidence == ""


def test_date_guess_serializes_the_public_contract():
    guess = DateGuess(
        year=1971,
        confidence=0.9,
        basis="publication line",
        evidence="Published 1971",
        alternatives=[1970],
    )

    assert guess.to_dict() == {
        "year": 1971,
        "confidence": 0.9,
        "basis": "publication line",
        "evidence": "Published 1971",
        "alternatives": [1970],
    }


def test_explicit_publication_line_beats_survey_year():
    text = (
        "AMBIENT AIR SURVEY IN MISSISSAUGA\n"
        "APRIL 1978\n"
        "ARB-TDA REPORT No. 51-80\n"
        "PUBLISHED AUGUST 1980\n"
        "Ontario Ministry of the Environment"
    )

    guess = infer_year_from_text(_item(), text)

    assert guess.year == 1980
    assert guess.basis == "publication line"
    assert 1978 in guess.alternatives
    assert guess.confidence >= 0.85
    _assert_verbatim(guess, text)


def test_copyright_line_beats_annual_report_period():
    text = (
        "HAMILTON WATER SUPPLY SYSTEM\n"
        "ANNUAL REPORT 1988\n"
        "FEBRUARY 1990\n"
        "Copyright: Queen's Printer for Ontario, 1990\n"
    )

    guess = infer_year_from_text(_item(), text)

    assert guess.year == 1990
    assert guess.basis == "copyright line"
    assert 1988 in guess.alternatives
    assert "1990" in guess.evidence
    _assert_verbatim(guess, text)


def test_same_year_publication_signals_are_not_reported_as_alternatives():
    text = "Published 1971\nCopyright Queen's Printer for Ontario, 1971\n"

    guess = infer_year_from_text(_item(), text)

    assert guess.year == 1971
    assert 1971 not in guess.alternatives
    assert len(guess.alternatives) == len(set(guess.alternatives))
    _assert_verbatim(guess, text)


def test_conflicting_original_publication_lines_cause_abstention():
    text = (
        "REPORT ON WATER QUALITY\n"
        "Published by authority of the Minister, 1968\n\n"
        "REPORT ON WATER QUALITY\n"
        "Published by authority of the Minister, 1974\n"
    )

    guess = infer_year_from_text(_item(), text)

    _assert_abstains(guess)
    assert set(guess.alternatives) >= {1968, 1974}


def test_structured_dated_covering_letter_is_recognized():
    pages = [
        _page(1, "ONTARIO WATER RESOURCES COMMISSION\nANNUAL REPORT"),
        _page(
            2,
            "December 31, 1969\n"
            "The Honourable Minister of the Environment\n"
            "Dear Sir:\n"
            "I have the honour to submit the enclosed report.\n"
            "Yours sincerely,\nCommissioner",
        ),
        _page(3, "CONTENTS\nIntroduction\nOperating results"),
    ]

    guess = infer_year_from_text(_item(), pages)

    assert guess.year == 1969
    assert guess.basis == "covering letter"
    assert guess.confidence >= 0.75
    _assert_verbatim(guess, pages)


def test_covering_letter_can_name_the_earlier_fiscal_period_it_transmits():
    pages = [
        _page(1, "DEPARTMENT OF PUBLIC WORKS\nANNUAL REPORT"),
        _page(
            2,
            "March 14, 1945\n"
            "The Honourable Provincial Secretary\n"
            "Dear Sir:\n"
            "I have the honour to submit the annual report for the fiscal year "
            "ended December 31, 1944.\n"
            "Yours sincerely,\nCommissioner",
        ),
    ]

    guess = infer_year_from_text(_item(), pages)

    assert guess.year == 1945
    assert guess.basis == "covering letter"
    assert 1944 in guess.alternatives
    _assert_verbatim(guess, pages)


def test_balance_sheet_date_is_not_a_covering_letter():
    text = (
        "RESERVE ACCOUNT\n"
        "Balance @ January 1, 1969  $57,217.75\n"
        "Deposited by Municipality   $7,634.86\n"
        "Balance @ December 31, 1969 $55,546.30\n"
    )

    _assert_abstains(infer_year_from_text(_item(), text))


def test_plain_text_opening_date_is_front_matter_not_a_proven_page():
    text = (
        "DUST SUPPRESSANT STUDY\n"
        "Ontario Ministry of the Environment\n"
        "March 1988\n"
        "Acres International Limited\n"
    )

    guess = infer_year_from_text(_item(), text)

    assert guess.year == 1988
    assert guess.basis == "front matter date"
    _assert_verbatim(guess, text)


def test_genuine_multi_page_input_can_identify_a_title_page():
    pages = [
        _page(1, "GOVERNMENT PUBLICATIONS\nLibrary cover"),
        _page(
            2,
            "BACKGROUND DATA\n"
            "Preliminary Report of the Committee on the Future Role\n"
            "of Universities in Ontario\n\n"
            "March 1981",
        ),
        _page(3, "CONTENTS\n1.0 ENROLMENT\n2.0 FORECASTS"),
    ]

    guess = infer_year_from_text(_item(), pages)

    assert guess.year == 1981
    assert guess.basis == "title page"
    _assert_verbatim(guess, pages)


def test_late_reference_to_another_publication_does_not_beat_title_page():
    pages = [
        _page(1, "COMMUNICATIONS NEWSLETTER\nNo. 4 March 1985"),
        _page(2, "CONTENTS\nSatellite policy\nPublic notices"),
        _page(
            5,
            "The consultation followed an earlier decision.\n"
            "Published September 15, 1984, that notice remained in force.\n",
        ),
    ]

    guess = infer_year_from_text(_item(), pages)

    assert guess.year == 1985
    assert guess.basis == "title page"
    assert guess.evidence in pages[0].text


@pytest.mark.parametrize(
    "text",
    [
        "AGENDAS/MINUTES BUSINESS COMMITTEE\nJANUARY 21, 1999\nAGENDA",
        "MEETING OF CITY COUNCIL\nTuesday, January 10, 1989\nAGENDA",
        "CITY ZONING BY-LAW NO. 98-17\nPASSED December 11, 1997",
        "LIST OF TABLES\nSampling Date, June 30, 1982\nIntroduction",
    ],
)
def test_event_record_dates_are_not_publication_dates(text):
    _assert_abstains(infer_year_from_text(_item(), text))


@pytest.mark.parametrize(
    "text",
    [
        "TENTATIVE DIAGNOSIS: survey animal\nNovember 22, 1982\nHISTOPATHOLOGY:",
        "Entered Civic Service April 1, 1913. Appointed Commissioner,\nOctober 1, 1941.",
        "Affordability of Housing\nJanuary 1978 - October, 1995\nChart values",
        "an examination of the 1952 Annual Report of the Department",
        '2. "Metropolitan Parks Development Report 1961", previous supplement',
        "In the 1963 report on Planning and Development Procedures we recommended",
    ],
)
def test_internal_record_and_cited_report_dates_are_rejected(text):
    _assert_abstains(infer_year_from_text(_item(), text))


@pytest.mark.parametrize(
    "text",
    [
        "Resigned September 30, 1969",
        "Pig Iron Capacity, January 1, 1978",
        "1 degree lecture 9 mai 2001",
        "operations bancaires jusqu'au 30 novembre 1980",
        "Statistics, Jan, 1980",
        "2, MAR 30 1949",
        "following extract from the Second Annual Report for 1908 minces no words",
        "edition. Reference Paper 55 (January 1955)",
    ],
)
def test_front_events_stamps_and_cited_works_are_not_publication_dates(text):
    _assert_abstains(infer_year_from_text(_item(), text))


def test_wrapped_citation_cue_blocks_prior_annual_report_date():
    text = (
        "The historical review quotes the\n"
        "following extract from the\n"
        "Second Annual Report for 1908 minces no words\n"
    )

    _assert_abstains(infer_year_from_text(_item(), text))


@pytest.mark.parametrize(
    "text",
    [
        "AS OF\nMarch 31, 2009",
        "PLANT CAPACITY\nJanuary 1, 1978",
        "DATA THROUGH\nMarch 31, 2009",
        "REFERENCE PAPER 55\nJanuary 1955",
    ],
)
def test_wrapped_nonpublication_label_blocks_front_date(text):
    _assert_abstains(infer_year_from_text(_item(), text))


@pytest.mark.parametrize("text", ["Published 1829", "Annual Report 2018"])
def test_year_outside_collection_span_is_rejected(text):
    _assert_abstains(infer_year_from_text(_item(), text))


def test_annual_report_for_year_ended_is_a_period_not_a_letter():
    text = "Annual report for the year ended 31 December 1972\nOperations and accounts"

    guess = infer_year_from_text(_item(), text)

    assert guess.year == 1972
    assert guess.basis == "annual report period"
    assert guess.confidence < 0.85
    _assert_verbatim(guess, text)


def test_annual_report_range_uses_end_year_and_preserves_start_as_alternative():
    text = "NATIONAL CAPITAL COMMISSION\nANNUAL REPORT 1962-1963\n"

    guess = infer_year_from_text(_item(), text)

    assert guess.year == 1963
    assert guess.basis == "annual report period"
    assert 1962 in guess.alternatives
    _assert_verbatim(guess, text)


def test_observed_data_table_yields_only_a_low_confidence_lower_bound():
    text = (
        "TABLE 6 - OPERATING RESULTS\n"
        "YEAR    FLOW    OPERATING COST\n"
        "1967    1415.5  48655.69\n"
        "1968    1460.2  51007.10\n"
        "1969    1475.0  53549.66\n"
    )

    guess = infer_year_from_text(_item(), text)

    assert guess.year == 1969
    assert guess.basis == "latest data year (lower bound)"
    assert guess.confidence < 0.65
    _assert_verbatim(guess, text)


@pytest.mark.parametrize(
    "future_word",
    ["PROJECTED", "FORECAST", "PLANNED", "SCENARIO", "TARGET"],
)
def test_future_year_table_is_not_a_publication_lower_bound(future_word):
    text = (
        f"TABLE 4 - {future_word} POPULATION\n"
        "YEAR    POPULATION\n"
        "1981    100000\n"
        "1986    120000\n"
        "1991    145000\n"
    )

    _assert_abstains(infer_year_from_text(_item(), text))


def test_projection_label_before_table_heading_blocks_future_bound():
    text = (
        "Population and employment projections guide future development.\n"
        "TABLE 2 - DISTRIBUTION BY MUNICIPALITY\n"
        "YEAR    POPULATION    EMPLOYMENT\n"
        "1971    401000        157000\n"
        "1981    450000        190000\n"
        "2001    550000        290000\n"
    )

    _assert_abstains(infer_year_from_text(_item(), text))


def test_years_in_prose_after_table_heading_are_not_table_rows():
    text = (
        "TABLE 4 - POPULATION HISTORY\n"
        "The depressed 1930s left population stable from 1932 to 1959 in that year.\n"
        "1949    5000\n"
        "1950    5050\n"
        "1951    5100\n"
    )

    guess = infer_year_from_text(_item(), text)

    assert guess.year == 1951
    assert guess.basis == "latest data year (lower bound)"


def test_year_led_prose_is_not_a_table_row_or_lower_bound():
    text = (
        "TABLE 4 - POPULATION HISTORY\n"
        "1930 was difficult; by 1940 conditions improved and in 1950 the city grew.\n"
    )

    _assert_abstains(infer_year_from_text(_item(), text))


def test_multiple_year_led_prose_lines_are_not_table_rows():
    text = (
        "TABLE 1 - NOTES\n"
        "1967 was the year 25 sites were tested.\n"
        "1968 was the year 30 sites were tested.\n"
        "1969 was the year 40 sites were tested.\n"
    )

    _assert_abstains(infer_year_from_text(_item(), text))


def test_earlier_observed_table_does_not_defeat_publication_line():
    text = (
        "Published 1971\n\n"
        "TABLE 1 - OBSERVED FLOW\n"
        "YEAR FLOW\n1968 2.1\n1969 2.4\n1970 2.8\n"
    )

    guess = infer_year_from_text(_item(), text)

    assert guess.year == 1971
    assert guess.basis == "publication line"
    _assert_verbatim(guess, text)


def test_observed_table_later_than_claimed_publication_causes_abstention():
    text = (
        "Published 1971\n\n"
        "TABLE 1 - OBSERVED FLOW\n"
        "YEAR FLOW\n1970 2.1\n1971 2.4\n1972 2.8\n"
    )

    guess = infer_year_from_text(_item(), text)

    _assert_abstains(guess)
    assert set(guess.alternatives) >= {1971, 1972}


@pytest.mark.parametrize(
    "text",
    [
        "Report on 8260 gal/ft/day weir loading",
        "The design capacity is 1980 gal/day.",
        "PROJECT NO. 2-1969-60",
        "CONTRACT 1971-04",
        "STATION 1968  WATER LEVEL",
        "SITE 1972  SAMPLE 4",
        "FILE NO. 1980-6",
        "DRAWING 1965-A",
        "REPORT NO. 1974-12",
        "Cat. No. T45-2/1997",
        "Inventory no. M27-01-673/1997",
        "See Smith (1988) and Jones (1990).",
        "The Environmental Protection Act, 1971 applies.",
        "This report discusses the Copyright Act, 1985.",
        "Digitized by the Internet Archive in 2015 with funding from a library.",
        "RECEIVED NOV 19 1971  UNIVERSITY LIBRARY",
        "Revised Statutes of Ontario, 1980",
        "1. Brochure created, printed and distributed at Mum Show 1998.",
        "MAY 07 1981",
        "© assist the community meeting its diversion goals by 1992",
        "Published results show that water quality improved in 1988.",
        "Revision of the 1988 estimates reduced costs.",
        "Copyright Provisions: material first published by another agency in 1971",
        "The budget covered fiscal year 1988. More funding was requested.",
        "Printed 2000 copies of this brochure.",
        "Third Printing 2000 copies.",
    ],
)
def test_year_shaped_non_dates_are_rejected(text):
    _assert_abstains(infer_year_from_text(_item(), text))


def test_street_number_does_not_beat_real_front_matter_date():
    text = (
        "Ontario Government Publications\n"
        "2001 Eglinton Avenue East\n"
        "Toronto, Ontario\n"
        "March, 1980\n"
    )

    guess = infer_year_from_text(_item(), text)

    assert guess.year == 1980
    assert 2001 not in guess.alternatives
    assert guess.basis == "front matter date"
    _assert_verbatim(guess, text)


def test_uncorroborated_spaced_digit_ocr_year_is_not_silently_corrected():
    text = "PROCEEDINGS OF THE WORKSHOP\nMAY, 19 8 8\n"

    _assert_abstains(infer_year_from_text(_item(), text))


def test_corrupted_ocr_year_cannot_override_clean_same_year_evidence():
    text = (
        "PROCEEDINGS OF THE WORKSHOP\n"
        "MAY, 19 8 8\n"
        "Copyright Queen's Printer for Ontario, 1988\n"
    )

    guess = infer_year_from_text(_item(), text)

    assert guess.year == 1988
    assert guess.basis == "copyright line"
    _assert_verbatim(guess, text)


@pytest.mark.parametrize(
    ("text", "year"),
    [
        ("Revised March 2001", 2001),
        ("Fourth Printing: November, 1983", 1983),
    ],
)
def test_explicit_revision_or_printing_is_a_publication_event(text, year):
    guess = infer_year_from_text(_item(), text)

    assert guess.year == year
    assert guess.basis == "publication line"
    _assert_verbatim(guess, text)


def test_bare_revision_inside_questionnaire_is_not_a_publication_event():
    text = (
        "ACCREDITATION SURVEY QUESTIONNAIRE\n"
        + "Section and response guidance\n" * 350
        + "Does the Governing Body have written Rules and Regulations?\n"
        "Council Directory 1986 - 88\n"
        "Revised in 1986\n"
        "Yes X\nNo ___\n"
    )

    _assert_abstains(infer_year_from_text(_item(), text))


@pytest.mark.parametrize("size", [4_500, 8_000])
def test_revision_in_middle_of_modest_document_is_not_a_colophon(size):
    text = "Narrative material.\n" * (size // 20) + "Revised March 2001\n"
    text += "More narrative material.\n" * (size // 25)

    _assert_abstains(infer_year_from_text(_item(), text))


def test_fiscal_year_heading_is_labeled_as_report_period():
    guess = infer_year_from_text(_item(), "Fiscal Year Ending March 1981")

    assert guess.year == 1981
    assert guess.basis == "annual report period"
    assert guess.confidence < 0.85


def test_wrapped_fiscal_year_date_is_not_upgraded_to_front_matter():
    text = "Fiscal Year Ending\nMarch 1981"

    _assert_abstains(infer_year_from_text(_item(), text))


def test_embedded_logo_copyright_is_not_the_document_imprint():
    text = (
        "CITIZENSHIP AND IMMIGRATION CANADA\n"
        "2008-2009 PERFORMANCE REPORT\n"
        + "Introduction and departmental results\n" * 180
        + "© 1996 Forest Stewardship Council\n"
    )

    guess = infer_year_from_text(_item(), text)

    assert guess.year != 1996


def test_french_publication_line_is_supported_without_fuzzy_matching():
    text = (
        "RAPPORT SUR LA QUALITÉ DE L'EAU\n"
        "Publié en 1971 par le ministère de l'Environnement\n"
    )

    guess = infer_year_from_text(_item(language="fre"), text)

    assert guess.year == 1971
    assert guess.basis == "publication line"
    _assert_verbatim(guess, text)


def test_french_covering_letter_is_recognized():
    pages = [
        _page(1, "COMMISSION DES RESSOURCES EN EAU\nRAPPORT"),
        _page(
            2,
            "Le 31 décembre 1969\n"
            "Monsieur le Ministre,\n"
            "J'ai l'honneur de vous soumettre le présent rapport.\n"
            "Veuillez agréer mes salutations distinguées.",
        ),
        _page(3, "TABLE DES MATIÈRES"),
    ]

    guess = infer_year_from_text(_item(language="fre"), pages)

    assert guess.year == 1969
    assert guess.basis == "covering letter"
    _assert_verbatim(guess, pages)


def test_empty_inputs_abstain():
    _assert_abstains(infer_year_from_text(_item(), ""))
    _assert_abstains(infer_year_from_text(_item(), []))


def test_existing_catalogue_year_is_never_overwritten():
    text = "Published 1971"

    guess = infer_year_from_text(_item(year=1969), text)

    _assert_abstains(guess)


def test_inference_does_not_mutate_item_or_pages():
    item = _item(title=["odd", "but legal", "metadata"])
    pages = [
        _page(1, "REPORT ON WATER QUALITY\nMarch 1981"),
        _page(2, "Introduction"),
    ]
    item_before = deepcopy(item)
    pages_before = deepcopy(pages)

    infer_year_from_text(item, pages)

    assert item == item_before
    assert pages == pages_before


@pytest.mark.parametrize(
    "text",
    [
        "Published 1971",
        "Copyright Queen's Printer, 1968",
        "Annual report for the year ended 31 December 1972",
        "No defensible date appears here.",
    ],
)
def test_public_result_invariants(text):
    guess = infer_year_from_text(_item(), text)

    assert isinstance(guess, DateGuess)
    assert 0.0 <= guess.confidence <= 1.0
    assert guess.year not in guess.alternatives
    assert len(guess.alternatives) == len(set(guess.alternatives))
    if guess.year is None:
        assert guess.evidence == ""
    else:
        _assert_verbatim(guess, text)


class _MetadataGuess:
    def __init__(self, year=None):
        self.year = year


def _no_metadata_year(item):
    return _MetadataGuess()


def test_recovery_cli_freezes_disjoint_samples_and_masks_validation_years():
    index = [
        {"identifier": f"unknown-{i}", "title": "Undated", "year": None}
        for i in range(5)
    ] + [
        {"identifier": f"known-{i}", "title": "Undated", "year": 1970 + i}
        for i in range(5)
    ]

    state = _new_state(
        index,
        unknown_n=3,
        validation_n=3,
        seed=42,
        validation_seed=43,
        collection="fixture",
        metadata_infer=_no_metadata_year,
    )

    assert len(state["selected"]["unknown"]) == 3
    assert len(state["selected"]["validation"]) == 3
    assert all(row["item"]["year"] is None for row in state["selected"]["validation"])
    assert all(isinstance(row["expected_year"], int) for row in state["selected"]["validation"])


def test_recovery_cli_separates_lower_bounds_from_date_precision():
    results = {
        "date": {
            "status": "guessed",
            "correct": True,
            "expected_year": 1971,
            "guess": {"year": 1971, "confidence": 0.9, "basis": "publication line"},
        },
        "bound": {
            "status": "guessed",
            "correct": False,
            "expected_year": 1972,
            "guess": {
                "year": 1971,
                "confidence": 0.3,
                "basis": "latest data year (lower bound)",
            },
        },
    }

    summary = _section_summary(2, results, validation=True)

    assert summary["exact_precision"] == 0.5
    assert summary["date_guess_exact_precision"] == 1.0
    assert summary["lower_bound_estimates"] == 1


def test_recovery_cli_refuses_a_checkpoint_from_another_detector(monkeypatch):
    monkeypatch.setattr("scripts.recover_years._detector_fingerprint", lambda: "new")
    state = {
        "detector_sha256": "old",
        "sampling": {
            "seed": 1,
            "validation_seed": 2,
            "unknown_sample": 3,
            "validation_sample": 4,
        },
    }
    args = Namespace(
        seed=1,
        validation_seed=2,
        unknown_sample=3,
        validation_sample=4,
    )

    with pytest.raises(ValueError, match="detector changed"):
        _check_resume(state, args)


def test_polite_delay_measures_from_previous_archive_completion(monkeypatch):
    timeline = iter([10.1])
    slept = []
    monkeypatch.setattr("scripts.recover_years.time.monotonic", lambda: next(timeline))
    monkeypatch.setattr("scripts.recover_years.time.sleep", slept.append)
    delay = _PoliteDelay(0.4)
    delay._last_finished = 10.0

    delay.wait()

    assert slept == [pytest.approx(0.3)]


def test_recovery_cli_spaces_metadata_and_ocr_requests():
    events = []

    class RecordingDelay:
        def wait(self):
            events.append("wait")

        def finished(self):
            events.append("finished")

    class RecordingArchive:
        def metadata(self, identifier):
            events.append(("metadata", identifier))
            return {"files": []}

        def ocr_text(self, identifier):
            events.append(("ocr", identifier))
            return "No defensible date"

    result = _one_result(
        RecordingArchive(),
        _item(),
        infer_year_from_text,
        RecordingDelay(),
    )

    assert result["status"] == "abstained"
    assert events == [
        "wait",
        ("metadata", "dating-fixture"),
        "finished",
        "wait",
        ("ocr", "dating-fixture"),
        "finished",
    ]


# -- whether a single value's year can be trusted ---------------------------

def test_a_comparison_sentence_is_flagged_not_silently_trusted():
    """Brantford 1969: "The average solids concentrations of 5.1% was less than
    the 1968 average of 5.3%" filed both numbers under 1969. 27 of the 56
    contested measurements in the first dispute-ledger run are this shape."""
    from groundtruth.dating import period_risk

    r = period_risk("The average solids concentrations of 5. 1% was less than "
                    "the 1968 average of 5.3%.", period="1969")
    assert not r.safe
    assert r.other_years == ["1968"]
    assert r.comparison


def test_an_ordinary_sentence_is_left_alone():
    from groundtruth.dating import period_risk

    r = period_risk("The average influent BOD was 104 mg/1.", period="1969")
    assert r.safe
    assert r.other_years == []


def test_the_report_s_own_year_in_its_own_sentence_is_not_another_year():
    from groundtruth.dating import period_risk

    r = period_risk("During 1963 the average daily flow was 5. 59 mgd.", period="1963")
    assert r.safe


def test_it_flags_rather_than_reassigning():
    """Deliberate, and decided by trying the other way first.

    A rule that moved values to the nearest year changed 14 records and got
    several wrong in a new direction: in "an increase of 0.7 percent over 1967
    flows" the 0.7 is the 1968 increase, not a 1967 value, and in "5.1% was less
    than the 1968 average" the 5.1 is the report's own. Telling those apart is
    grammar, not proximity, and an invisible wrong year turns a flat series into
    a trend.
    """
    from groundtruth.dating import period_risk

    r = period_risk("representing an increase of 0. 7 percent over 1967 flows.",
                    period="1968")
    assert r.period == "1968"          # unchanged
    assert not r.safe                  # but not trusted either
