"""Tests for the vision path.

The prose path's guard is "quote the sentence, and I will check it is on the
page". A table has no sentences, so the vision equivalent is "say which row and
column you read this under, and I will check those exist".

That check is not optional decoration. Run against a phosphorus probability plot,
a local vision model returned five values labelled "Phosphorus / Month" for a
page with no monthly columns whatsoever -- it invented the table structure, and
every fabricated record carried labels and so passed a mere presence check.
"""

from __future__ import annotations

import pytest

from groundtruth.models import PageText
from groundtruth.vision import _label_on_page, extract_table


PLOT_PAGE_OCR = (
    "PHOSPHORUS .\n\n0 2\n\n0.1 1 1 1 1 1 1 1 1\n\n"
    "2 5 10 20 30 4 0 50 6 0 70 80 9 0 95 98\n\n"
    "PERCENTAGE OF SAMPLES EQUAL TO, OR LESS THAN\n\n12"
)


class FakeVision:
    name = "fake-vision"

    def __init__(self, response: str) -> None:
        self.response = response

    def read_image(self, system, prompt, image):  # noqa: ANN001, D102
        return self.response


def _page(text: str = PLOT_PAGE_OCR) -> PageText:
    return PageText(identifier="ident", page=14, text=text)


# -- label verification ------------------------------------------------------

@pytest.mark.parametrize(
    ("label", "present"),
    [
        ("Phosphorus", True),
        ("PERCENTAGE OF SAMPLES", True),
        ("Month", False),
        ("Effluent quality", False),
    ],
)
def test_labels_are_checked_against_surviving_ocr(label, present):
    """OCR destroys table VALUES but usually keeps HEADINGS, which are set in
    larger cleaner type. That makes the OCR text the right thing to check
    against, at the cost of one substring search."""
    assert _label_on_page(label, PLOT_PAGE_OCR) is present


def test_fabricated_structure_is_rejected():
    """The real llava failure, frozen as a test."""
    result = extract_table(
        _page(),
        b"",
        client=FakeVision(
            '[{"kind":"observation","parameter":"phosphorus","value":0.2,'
            '"unit":"mg/L","confidence":0.5,"row_label":"Phosphorus",'
            '"column_label":"Month"}]'
        ),
    )
    assert result.kept == 0
    assert "may have invented the table structure" in result.rejected[0]["why"]


def test_a_real_label_survives():
    result = extract_table(
        _page(),
        b"",
        client=FakeVision(
            '[{"kind":"observation","parameter":"phosphorus","value":0.3,'
            '"unit":"mg/L","confidence":0.5,"row_label":"Phosphorus",'
            '"column_label":"PERCENTAGE OF SAMPLES"}]'
        ),
    )
    assert result.kept == 1
    assert "Phosphorus" in result.records[0].provenance.source_text


def test_cell_with_no_coordinates_is_rejected():
    """A cell nobody can find again cannot be disagreed with."""
    result = extract_table(
        _page(),
        b"",
        client=FakeVision(
            '[{"kind":"observation","parameter":"phosphorus","value":42,'
            '"unit":"mg/L","confidence":0.9}]'
        ),
    )
    assert result.kept == 0
    assert "not locatable" in result.rejected[0]["why"]


def test_unreadable_digit_is_dropped_not_guessed():
    result = extract_table(
        _page(),
        b"",
        client=FakeVision(
            '[{"kind":"observation","parameter":"phosphorus","value":null,'
            '"unit":"mg/L","row_label":"Phosphorus"}]'
        ),
    )
    assert result.kept == 0
    assert "no numeric value" in result.rejected[0]["why"]


# -- confidence --------------------------------------------------------------

def test_vision_confidence_is_capped_below_the_prose_path():
    """Reading a degraded table is harder than reading a clean sentence, and the
    OCR-confidence signal does not apply to an image at all."""
    result = extract_table(
        _page(),
        b"",
        client=FakeVision(
            '[{"kind":"observation","parameter":"phosphorus","value":0.3,'
            '"unit":"mg/L","confidence":1.0,"row_label":"Phosphorus"}]'
        ),
    )
    assert result.records[0].confidence <= 0.8


def test_provenance_records_the_vision_path():
    result = extract_table(
        _page(),
        b"",
        client=FakeVision(
            '[{"kind":"design","parameter":"BOD","value":180,"unit":"mg/L",'
            '"confidence":0.9,"row_label":"PHOSPHORUS"}]'
        ),
    )
    assert result.records[0].provenance.path == "vision"
    assert result.records[0].provenance.extractor == "fake-vision"


def test_no_ocr_text_falls_back_to_trusting_the_model():
    """Some pages are pure image with no text layer at all. Refusing everything
    there would discard the pages the vision path exists to serve."""
    result = extract_table(
        _page(text=""),
        b"",
        client=FakeVision(
            '[{"kind":"observation","parameter":"phosphorus","value":0.3,'
            '"unit":"mg/L","confidence":0.5,"row_label":"Anything","column_label":"At All"}]'
        ),
    )
    assert result.kept == 1


# -- the census page that was rejected entirely ------------------------------

CENSUS_OCR = (
    "Tableau 1. Certaines repartitions de la population, des logements "
    "CT - SR CT - SR CT - SR CT - SR CT - SR "
    "135.02 135.03 136.01 136.02 137.01 Caracteristiques "
    "STATUT PROFESSIONNEL 1,825 790 1,780 1,070 910 "
    "Hommes - Tous les statuts professionnels"
)


def test_a_header_the_ocr_split_apart_is_still_found():
    """The control rejected all 25 records on a Statistics Canada page.

    A column heading reads "CT - SR 135.03", and the OCR of that header row runs
    "CT - SR CT - SR CT - SR ... 135.02 135.03 136.01" -- every word and every
    number present, none of them adjacent. The label was therefore nowhere on
    the page as a contiguous string, though every part of it was, and the values
    the model returned were exactly right.
    """
    from groundtruth.vision import _label_on_page

    assert _label_on_page("CT - SR 135.03", CENSUS_OCR)
    assert _label_on_page("Hommes - Tous les statuts professionnels", CENSUS_OCR)


def test_a_heading_that_is_not_on_the_page_is_still_refused():
    """Weakening the check must not disarm it.

    The short-token path is the one that changed, and it now requires every part
    to be present somewhere -- so a fabricated column reference still fails,
    because its numbers are not on the page.

    The long-token path is unchanged and deliberately lenient: one substantial
    shared token is enough, on the argument that OCR mangles headings and a
    label sharing nothing at all is the real fabrication signal. "Population
    totale par comte" therefore passes on the strength of "population", which is
    the documented intent rather than a defect.
    """
    from groundtruth.vision import _label_on_page

    assert not _label_on_page("CT - SR 999.99", CENSUS_OCR)
    assert not _label_on_page("Superficie des exploitations agricoles", CENSUS_OCR)


def test_a_count_needs_no_unit():
    """The vision path's version of the water-report bias.

    A census count of 1,825 men has no mg/L to give. Requiring a unit symbol
    discarded every record on the page.
    """
    from groundtruth.models import Provenance, Record

    counted = Record(kind="observation", parameter="Hommes - Tous les statuts",
                     value=1825, unit=None, confidence=0.9,
                     provenance=Provenance("x", 1, "a sentence"))
    assert counted.problems() == []

    measured = Record(kind="observation", parameter="BOD", value=104, unit=None,
                      confidence=0.9, provenance=Provenance("x", 1, "a sentence"))
    assert "no unit" in measured.problems()


def test_the_counted_table_does_not_match_inside_other_words():
    """"men" must not match "development", which the boundary-free version did
    after a backspace byte ate the word boundaries."""
    from groundtruth.models import _COUNTED_PARAMETER

    assert not _COUNTED_PARAMETER.search("development cost")
    assert not _COUNTED_PARAMETER.search("suspended solids")
    assert _COUNTED_PARAMETER.search("elementary schools")


def test_no_source_file_carries_a_control_byte():
    """A `\b` written through a shell heredoc becomes a literal backspace.

    The file then reads back correctly in every editor and the pattern matches
    nothing -- which is how "elementary schools" failed to match `schools?`.
    This has now happened twice in this project.
    """
    import pathlib

    offenders = []
    for path in pathlib.Path("groundtruth").rglob("*.py"):
        raw = path.read_bytes()
        if any(b < 9 or (13 < b < 32) for b in raw):
            offenders.append(path.name)
    assert offenders == []


def test_a_page_that_can_find_nothing_is_not_allowed_to_refuse_everything():
    """The control fired hardest exactly where vision matters most.

    Georgian Bay Ship Canal, 1909: a full table page whose text layer came back
    as about 1,000 characters, and all 30 candidate records rejected for
    headings that are simply not in it. That is the circumstance the vision path
    exists for, so a check that discards most confidently there is inverted --
    strictest where it can judge least.

    A minimum character count was the first fix and was too blunt: the plot page
    that catches an invented "Phosphorus / Month" carries about 150 characters,
    so no cutoff separates the two. The page therefore calibrates itself.
    """
    from groundtruth.vision import _page_can_referee

    destroyed = "STATEMENT No. 4 Continued. SUMMIT WATER SUPPLY. OCTOBER, 1905."
    claims = [{"row_label": "Talon Lake storage", "column_label": "Evaporation"}]
    assert not _page_can_referee(claims, destroyed)

    # The plot page finds one of the two labels, so it has proved it can judge.
    plot_claims = [{"row_label": "Phosphorus", "column_label": "Month"}]
    assert _page_can_referee(plot_claims, PLOT_PAGE_OCR)


def test_a_page_that_cannot_referee_keeps_the_record_and_says_why():
    """Weaker evidence should travel with the record, not be forgotten."""
    result = extract_table(
        _page(text="STATEMENT No. 4 Continued. SUMMIT WATER SUPPLY."),
        b"",
        client=FakeVision(
            '[{"kind":"observation","parameter":"discharge","value":41.2,'
            '"unit":"cu ft","confidence":0.6,"row_label":"Talon Lake",'
            '"column_label":"Evaporation"}]'
        ),
    )
    assert result.kept == 1
    assert "not checked" in result.records[0].raw["label_check"]


def test_columns_that_measure_different_things_get_different_parameters():
    """A table is two-dimensional; a parameter name is not.

    An expenditure table gives In-House 15, Contracts 100 and Total 115 for one
    year -- three measurements whose only distinguishing feature is the column.
    Sharing an identity, they reach the dispute ledger as a three-way
    contradiction about a department's budget.
    """
    ocr = ("PROGRAM EXPENDITURES ($000) In-House Contracts Total "
           "1981-82 15 100 115")
    result = extract_table(
        _page(text=ocr),
        b"",
        client=FakeVision(
            '[{"kind":"observation","parameter":"expenditures ($000)","value":15,'
            '"unit":"$000","confidence":0.8,"row_label":"1981-82","column_label":"In-House"},'
            '{"kind":"observation","parameter":"expenditures ($000)","value":100,'
            '"unit":"$000","confidence":0.8,"row_label":"1981-82","column_label":"Contracts"},'
            '{"kind":"observation","parameter":"expenditures ($000)","value":115,'
            '"unit":"$000","confidence":0.8,"row_label":"1981-82","column_label":"Total"}]'
        ),
    )
    assert result.kept == 3
    names = {r.parameter for r in result.records}
    assert len(names) == 3
    assert any("In-House" in n for n in names)


def test_a_single_column_adds_nothing_and_is_left_alone():
    """Only disambiguate where there is an ambiguity to resolve."""
    ocr = "MONTH MAX. DAILY Flow Jan. 6.976 Feb. 6.200"
    result = extract_table(
        _page(text=ocr),
        b"",
        client=FakeVision(
            '[{"kind":"observation","parameter":"MAX. DAILY Flow","value":6.976,'
            '"unit":"mgd","confidence":0.8,"row_label":"Jan.","column_label":"MAX. DAILY Flow"},'
            '{"kind":"observation","parameter":"MAX. DAILY Flow","value":6.2,'
            '"unit":"mgd","confidence":0.8,"row_label":"Feb.","column_label":"MAX. DAILY Flow"}]'
        ),
    )
    assert {r.parameter for r in result.records} == {"MAX. DAILY Flow"}
