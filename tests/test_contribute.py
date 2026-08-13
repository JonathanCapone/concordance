"""Tests for accepting readings from strangers.

The property under test is that nothing depends on trusting the contributor.
Every check asks the archive, not the submitter, and the tests are written as
attacks rather than happy paths.
"""

from __future__ import annotations

import copy

import pytest

from concordance.contribute import (
    _value_in_quote,
    bundle_id,
    make_bundle,
    merge_bundle,
    verify_bundle,
)


class FakeArchive:
    """Stands in for archive.org. The point of the design is that the referee is
    external, so in tests it is simply a different external thing."""

    def __init__(self, pages: dict[int, str]) -> None:
        self._pages = pages

    def pages(self, identifier: str):  # noqa: D102
        class P:
            def __init__(self, n, t):
                self.page, self.text = n, t
        return [P(n, t) for n, t in self._pages.items()]


REAL_PAGE = (
    "PLANT EFFICIENCY\n\nThe average influent BOD and suspended solids were "
    "104 mg/1 and 224 mg/1 respectively. The average effluent BOD and suspended "
    "solids were 37 mg/1 and 36 mg/1 respectively.\n\nJust over three million "
    "gallons of raw sludge were pumped to the digesters."
)


def _record(value, quote, page=11, key="k1"):
    return {
        "key": key, "kind": "observation", "parameter": "BOD", "value": value,
        "unit": "mg/L",
        "provenance": {"identifier": "item1", "page": page, "source_text": quote},
    }


def _archive():
    return FakeArchive({11: REAL_PAGE})


# -- the honest case ---------------------------------------------------------

def test_a_real_reading_verifies():
    b = make_bundle([_record(104, "The average influent BOD and suspended solids were 104 mg/1")])
    v = verify_bundle(b, archive=_archive())
    assert v.verified == 1 and v.accepted


# -- the attacks -------------------------------------------------------------

def test_fabricated_sentence_is_rejected():
    b = make_bundle([_record(104, "The plant discharged 104 mg/1 of pure virtue.")])
    v = verify_bundle(b, archive=_archive())
    assert not v.accepted
    assert "not on that page" in v.failed[0]["why"]


def test_altered_number_with_a_real_sentence_is_rejected():
    """The obvious way to poison a contribution, and the one a sentence check
    alone cannot see: keep the true quote, change the number."""
    b = make_bundle([_record(99999, "The average influent BOD and suspended solids were 104 mg/1")])
    v = verify_bundle(b, archive=_archive())
    assert not v.accepted
    assert "does not appear in the sentence" in v.failed[0]["why"]


def test_one_bad_record_rejects_the_whole_bundle():
    """Not a threshold. A single fabricated sentence means the submission was not
    produced the way it claims, so keeping the parts that happened to pass would
    be trusting the contributor after catching them."""
    b = make_bundle([
        _record(104, "The average influent BOD and suspended solids were 104 mg/1", key="a"),
        _record(37, "A sentence that is nowhere on the page", key="b"),
    ])
    v = verify_bundle(b, archive=_archive())
    assert v.verified == 1 and not v.accepted


def test_wrong_page_is_rejected():
    b = make_bundle([_record(104, "The average influent BOD", page=99)])
    v = verify_bundle(b, archive=_archive())
    assert not v.accepted


# -- what it deliberately does NOT fail on -----------------------------------

def test_a_value_written_in_words_is_now_read_rather_than_excused():
    """"Just over three million gallons" really is where 3000000 comes from.

    This used to assert "unchecked" -- the honest answer available to a check
    that could only see digits. It is now VERIFIED, because concordance.numerals
    reads the words, and the reason says which allowance was made. The old
    assertion was not wrong when it was written; it recorded a limit that has
    since been removed.
    """
    state, why = _value_in_quote(3000000, "Just over three million gallons of raw sludge")
    assert state == "ok"
    assert "in words" in why


def test_a_bare_article_still_proves_nothing():
    """The risk that comes with reading words: "one" must not support 1."""
    state, _ = _value_in_quote(1, "one of the plants was taken out of service")
    assert state == "failed"


def test_ocr_spacing_inside_a_number_still_matches():
    state, _ = _value_in_quote(8.8, "The maximum daily flow was 8. 8 million gallons")
    assert state == "ok"


def test_thousands_separators_do_not_break_it():
    state, _ = _value_in_quote(53549.66, "The total operating cost was $53, 549. 66")
    assert state == "ok"


@pytest.mark.parametrize(
    ("fabricated", "sentence"),
    [
        (12, "The value was 3120 mg/L."),
        (1, "The value was 10 mg/L."),
        (5, "The total operating cost was $53,549.66."),
        (5, "The temperature was -5 C."),
        (-5, "The temperature was 5 C."),
    ],
)
def test_a_digit_substring_is_not_the_number_the_sentence_states(fabricated, sentence):
    state, _ = _value_in_quote(fabricated, sentence)
    assert state == "failed"


# -- merging -----------------------------------------------------------------

def test_merge_refuses_an_unverified_bundle():
    b = make_bundle([_record(104, "anything")])
    with pytest.raises(ValueError):
        merge_bundle(b, verdict=None)


def test_merge_refuses_a_failed_bundle(tmp_path):
    b = make_bundle([_record(104, "A sentence that is nowhere on the page")])
    v = verify_bundle(b, archive=_archive())
    with pytest.raises(ValueError):
        merge_bundle(b, into=tmp_path, verdict=v)


def test_the_same_reading_submitted_twice_is_one_bundle():
    """Content-addressed, so two people reading the same page collide rather than
    duplicating, and neither copy is privileged."""
    a = _record(104, "The average influent BOD and suspended solids were 104 mg/1")
    assert bundle_id([a]) == bundle_id([copy.deepcopy(a)])


def test_merge_drops_records_already_held(tmp_path):
    quote = "The average influent BOD and suspended solids were 104 mg/1"
    b = make_bundle([_record(104, quote)])
    v = verify_bundle(b, archive=_archive())
    first = merge_bundle(b, into=tmp_path, verdict=v)
    assert first["accepted"] == 1
    second = merge_bundle(b, into=tmp_path, verdict=v)
    assert second["accepted"] == 0 and second["duplicates_dropped"] == 1
