"""Tests for metadata repair.

The governing rule is that a repair which guesses is worse than one that
abstains: this produces a diff intended to be offered back to a real catalogue,
and a confident wrong correction is harder to undo than a missing one.
"""

from __future__ import annotations

import pytest

from concordance.repair import infer_year, normalize_language, repair


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("eng", ["eng"]),
        ("English", ["eng"]),
        ("Eng", ["eng"]),
        ("ENG", ["eng"]),
        ("fre", ["fre"]),
        ("fra", ["fre"]),
        ("French", ["fre"]),
        ("FRA", ["fre"]),
        ("eng-fre", ["mul"]),
        ("und", ["und"]),
    ],
)
def test_language_spellings_collapse(raw, expected):
    codes, unresolved = normalize_language(raw)
    assert codes == expected
    assert unresolved == []


def test_unknown_language_is_surfaced_not_guessed():
    """`n-cn-on` is a MARC *geographic* code that ended up in the language field.

    Anything resembling it must be reported, never coerced -- a repair pass that
    quietly turned it into "eng" would erase evidence of a real catalogue defect.
    """
    codes, unresolved = normalize_language("n-cn-on")
    assert codes == []
    assert unresolved == ["n-cn-on"]


def test_obsolete_exonym_is_not_silently_remapped():
    """`esk` is an outdated term for Inuit languages. Mapping it is a decision
    about people, not a string operation, so this module refuses to make it."""
    codes, unresolved = normalize_language("esk")
    assert codes == []
    assert unresolved == ["esk"]


def test_multiple_languages_deduplicate():
    codes, _ = normalize_language(["eng", "English", "ENG", "fre"])
    assert codes == ["eng", "fre"]


# -- year --------------------------------------------------------------------

def test_single_year_in_title_is_high_confidence():
    g = infer_year({"title": "Amherstburg area water system : annual report - 1986 /"})
    assert g.year == 1986
    assert g.confidence >= 0.85


def test_year_range_takes_the_later_year_with_lower_confidence():
    """A reporting period '1979-1980' is published at or after its end, but this
    is an inference and is scored as one."""
    g = infer_year({"title": "An assessment of pesticide research projects 1979-1980"})
    assert g.year == 1980
    assert g.confidence < 0.85
    assert 1979 in g.alternatives


def test_several_unrelated_years_are_low_confidence():
    g = infer_year({"title": "Reports covering 1965, 1972 and 1988 operations"})
    assert g.year == 1988
    assert g.confidence <= 0.5


def test_item_that_already_has_a_year_is_left_alone():
    assert infer_year({"year": "1969", "title": "annual report 1969"}).year is None


def test_no_year_anywhere_yields_nothing():
    g = infer_year({"title": "Basic sewage treatment operation."})
    assert g.year is None
    assert g.confidence == 0.0


def test_four_digit_numbers_that_are_not_years_are_ignored():
    g = infer_year({"title": "Report on 8260 gal/ft/day weir loading"})
    assert g.year is None


# -- end to end --------------------------------------------------------------

def test_repair_proposes_without_mutating_input():
    items = [
        {"identifier": "a", "language": "English", "title": "annual report 1971"},
        {"identifier": "b", "language": "eng", "year": "1969", "title": "x"},
    ]
    snapshot = [dict(i) for i in items]
    report = repair(items)

    assert items == snapshot, "repair must never mutate the catalogue it reads"

    fields = {(p.identifier, p.field) for p in report.proposals}
    assert ("a", "language") in fields
    assert ("a", "year") in fields
    # b is already correct and already dated; nothing to propose.
    assert not any(p.identifier == "b" for p in report.proposals)


def test_low_confidence_guesses_can_be_excluded():
    items = [{"identifier": "c", "title": "covering 1965, 1972 and 1988"}]
    assert repair(items, min_confidence=0.9).proposals == []
    assert repair(items, min_confidence=0.3).proposals != []
