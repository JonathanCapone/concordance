"""Tests for the picture attached to a number.

A crop is believed more readily than a page number, so the failure that matters
here is a citation that points confidently at the wrong place. Every test is
about refusing to do that rather than about producing a nice picture.

No network: the IIIF id resolver is stubbed, because what needs testing is the
geometry and the refusals, not archive.org.
"""

from __future__ import annotations

import pytest

from concordance import citations
from concordance.citations import Citation, cite, cite_cell, cite_record
from concordance.models import PageText, Word


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(citations, "iiif_base",
                        lambda ident, index, **kw: f"BASE/{ident}/{index}")


def _word(text, x0, y0, x1, y1):
    return Word(text=text, x0=x0, y0=y0, x1=x1, y1=y1)


def _page():
    """A tiny table: a row label, two column headers, on a 1000x1000 page."""
    return PageText(
        identifier="doc", page=15, width=1000, height=1000,
        text="TABLE I Jan. MAX. DAILY r low MIN. DAILY r low",
        words=[
            _word("TABLE", 400, 50, 500, 80),
            _word("Jan.", 100, 400, 160, 430),
            _word("MAX.", 300, 200, 380, 230),
            _word("DAILY", 390, 200, 470, 230),
            _word("MIN.", 600, 200, 660, 230),
            _word("DAILY", 670, 200, 750, 230),
        ],
    )


# -- the index that could point at the wrong page ---------------------------

def test_bookreader_and_iiif_number_the_same_page_differently():
    """Verified by fetching both and looking: BookReader n14 and IIIF $15 are
    the same sheet. Using one index for the other silently returns the
    preceding leaf, which is the worst thing this module could do."""
    c = Citation(identifier="doc", page=15)
    assert c.leaf == 14
    assert c.iiif_index == 15
    assert "/page/n14/" in c.page_url
    assert "/doc/15" in c.crop_url


def test_page_one_does_not_produce_a_negative_leaf():
    assert Citation(identifier="doc", page=1).leaf == 0
    assert Citation(identifier="doc", page=0).leaf == 0


# -- prose ------------------------------------------------------------------

def test_a_quote_is_cropped_to_its_own_words():
    page = PageText(
        identifier="doc", page=3, width=1000, height=1000,
        text="The waste water enters the plant",
        words=[_word("The", 100, 500, 140, 530),
               _word("waste", 150, 500, 220, 530),
               _word("water", 230, 500, 300, 530)],
    )
    c = cite(page, "The waste water")
    assert c.kind == "quote"
    x, y, w, h = c.box
    assert x < 100 and y < 500          # padded outward
    assert x + w > 300 and y + h > 530
    assert f"{x},{y},{w},{h}" in c.crop_url


def test_a_quote_that_is_not_on_the_page_degrades_and_says_so():
    c = cite(_page(), "a sentence from a different document entirely")
    assert c.kind == "page"
    assert c.box is None
    assert "whole page" in c.note
    assert not c.exact


def test_a_crop_never_leaves_the_page():
    page = PageText(identifier="doc", page=1, width=200, height=200, text="x",
                    words=[_word("x", 180, 180, 199, 199)])
    x, y, w, h = cite(page, "x").box
    assert x >= 0 and y >= 0
    assert x + w <= 200 and y + h <= 200


# -- table cells ------------------------------------------------------------

def test_a_cell_is_the_crossing_of_its_row_and_column():
    c = cite_cell(_page(), "Jan.", "MAX. DAILY")
    assert c.kind == "cell"
    x, y, w, h = c.box
    assert x < 300 and x + w > 470       # spans the column header
    assert y < 400 and y + h > 430       # spans the row label
    assert y > 230                       # and does NOT reach up to the header row


def test_a_label_the_model_read_better_than_ocr_still_matches():
    """The seam of the whole idea: the vision model returns the heading as it
    appears on the scan, "MAX. DAILY Flow", while the word list holds what OCR
    made of it, "MAX. DAILY r low". Shortening from the right recovers it -- a
    shorter match is a wider crop, never a wrong one."""
    c = cite_cell(_page(), "Jan.", "MAX. DAILY Flow")
    assert c.kind == "cell"


def test_a_cell_that_swells_to_most_of_the_page_is_refused():
    """A multi-word label whose words are scattered spans the whole page.

    The crossing of a row and a column is normally small even when the two
    labels are far apart -- that is the point of the construction. It only
    swells when one label MATCHES across a wide span, which happens when OCR
    puts the words of a heading in different places. The result is a rectangle
    that is evidence of nothing, and cropping to it would dress a failure up as
    a citation.
    """
    page = PageText(
        identifier="doc", page=1, width=1000, height=1000,
        text="TOTAL top left ... MONTHLY bottom right",
        words=[
            _word("TOTAL", 10, 10, 90, 40),
            _word("MONTHLY", 900, 940, 990, 980),   # same label, other corner
            _word("ROW", 20, 20, 60, 900),          # a row label spanning the page
        ],
    )
    c = cite_cell(page, "ROW", "TOTAL MONTHLY")
    assert c.kind == "page"
    assert "too much to be one cell" in c.note


def test_a_missing_label_names_which_one_was_missing():
    c = cite_cell(_page(), "Feb.", "MAX. DAILY")
    assert c.kind == "page"
    assert "row label" in c.note


# -- dispatch ---------------------------------------------------------------

def test_a_vision_record_is_cited_as_a_cell_and_a_prose_one_as_a_quote():
    page = _page()
    vision = {"provenance": {"source_text": "table cell [Jan. / MAX. DAILY Flow]"}}
    assert cite_record(page, vision).kind == "cell"

    prose = {"provenance": {"source_text": "TABLE"}}
    assert cite_record(page, prose).kind == "quote"


def test_a_record_with_no_evidence_shows_the_page_rather_than_inventing_one():
    assert cite_record(_page(), {"provenance": {}}).kind == "page"
    assert cite_record(_page(), {}).kind == "page"


# -- a sentence that wraps ---------------------------------------------------

def _wrapped_page():
    """Three lines of a paragraph, as the OCR word list holds them."""
    words = []
    line1 = "It is seen that the Commission's objective for BOD".split()
    line2 = "was exceeded only 20 per cent of the time and for SS 45 per".split()
    line3 = "cent of the time. The reason for the higher concentration".split()
    for y, line in ((100, line1), (200, line2), (300, line3)):
        x = 200
        for tok in line:
            words.append(_word(tok, x, y, x + 40, y + 30))
            x += 50
    # A caption far to the left on the middle line, to prove widening picks up
    # everything on the lines the crop covers.
    words.append(_word("margin", 40, 200, 90, 230))
    return PageText(identifier="doc", page=35, width=2000, height=1000,
                    text=" ".join(w.text for w in words), words=words)


def test_a_wrapped_sentence_crops_to_the_whole_passage():
    """The bug that produced citations reading "It is seen that the C".

    find_boxes returns a contiguous run and degrades to the longest matching
    OPENING run, which it does often -- OCR mangles the middle of a sentence
    more than its start. Cropping to that alone gives the right sentence and
    useless evidence.
    """
    page = _wrapped_page()
    quote = ("It is seen that the Commission's objective for BOD was exceeded "
             "only 20 per cent of the time and for SS 45 per cent of the time.")
    c = cite(page, quote)
    assert c.kind == "quote"
    x, y, w, h = c.box
    assert y < 100 and y + h > 230        # reaches the last matched line
    assert h > 130                        # more than one line tall


def test_widening_picks_up_text_on_the_lines_it_covers():
    """A box drawn only round the matched words slices the intervening lines."""
    page = _wrapped_page()
    c = cite(page, "It is seen that the Commission's objective for BOD was exceeded")
    x, _, w, _ = c.box
    assert x < 90                          # includes the left-margin word


def test_a_tail_match_earlier_on_the_page_does_not_stretch_the_crop_backwards():
    """A phrase repeated above the quote must not drag the box up over
    unrelated text."""
    words = [_word("the", 100, 900, 140, 930), _word("time", 150, 900, 200, 930)]
    words += [_word(t, 100 + 50 * i, 100, 140 + 50 * i, 130)
              for i, t in enumerate("It is seen that the Commission".split())]
    page = PageText(identifier="doc", page=1, width=1000, height=1000,
                    text=" ".join(w.text for w in words), words=words)
    c = cite(page, "It is seen that the Commission")
    _, y, _, h = c.box
    assert y + h < 500                     # did not reach down to the decoy
