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
