"""Tests for the archive-native tool layer.

The property under test throughout is not "does it return an answer" but "can a
reader check the answer, and is the answer honest about what it compared
against". A tool that quietly judges a 1963 measurement by a 2026 guideline
produces a damning, confident, meaningless verdict.
"""

from __future__ import annotations

import json

import pytest

from concordance.models import Provenance, Record
from concordance.tools import (
    Corpus,
    explain_this_number,
    find_my_town,
    read_me_the_record,
    show_the_page,
)


def _rec(year, param, value, unit, place="Owen Sound", kind="observation", src="a sentence"):
    return Record(
        kind=kind, parameter=param, value=value, unit=unit, place=place,
        period=str(year), confidence=0.9,
        provenance=Provenance(identifier="ident1", page=11, source_text=src),
    )


@pytest.fixture
def corpus():
    return Corpus(
        records=[
            _rec(1963, "BOD removal", 46.4, "%"),
            _rec(1964, "biochemical oxygen demand removal", 46.4, "%"),
            _rec(1965, "BOD removal", 52.0, "%"),
            _rec(1966, "BOD removal", 58.0, "%"),
            _rec(1967, "BOD removal", 61.0, "%"),
            _rec(1969, "BOD removal", 64.0, "%"),
            _rec(1963, "Design Population", 25000, "persons", kind="design"),
        ],
        places=["Owen Sound"],
    )


# -- explain_this_number -----------------------------------------------------

def test_removal_verdict_uses_era_appropriate_context():
    out = explain_this_number("BOD removal", 46.4, "%", 1963)
    assert "46.4%" in out["verdict"]
    assert "primary treatment" in out["verdict"].lower()


def test_modern_comparison_is_labelled_as_such():
    """The reader must not mistake 'worse than today' for 'illegal at the time'."""
    out = explain_this_number("BOD", 37, "mg/L", 1969)
    assert "MODERN" in out["caveat"]
    assert "rules of its own time" in out["caveat"]
    assert "modern" in out["compared_against"]


def test_era_standard_is_preferred_over_the_modern_benchmark():
    out = explain_this_number("BOD", 37, "mg/L", 1969, era_standard=45)
    assert "within" in out["verdict"] and "45" in out["verdict"]
    assert "caveat" not in out, "no modern-benchmark caveat when the real limit is known"


def test_verdict_reads_as_a_sentence():
    """Regression: a sentence was being interpolated where a noun phrase belonged,
    producing 'is about 1.5x modern Ontario effluent is commonly held near...'."""
    v = explain_this_number("BOD", 37, "mg/L", 1969)["verdict"]
    assert "x modern Ontario effluent is" not in v
    assert "times the modern 25 mg/L benchmark" in v


def test_unknown_parameter_is_not_interpreted():
    out = explain_this_number("widget throughput", 5, "each", 1970)
    assert "verdict" not in out
    assert "has not been interpreted" in out["explanation"]


# -- find_my_town ------------------------------------------------------------

def test_find_my_town_merges_synonyms_when_counting(corpus):
    """'BOD removal' and 'biochemical oxygen demand removal' are one measurement."""
    out = find_my_town(corpus, "Owen Sound")
    measured = dict(out["measured"])
    assert measured.get("bod removal") == 6
    assert "biochemical oxygen demand removal" not in measured


def test_find_my_town_is_case_insensitive(corpus):
    assert find_my_town(corpus, "owen sound")["found"]


def test_unknown_town_lists_what_is_available(corpus):
    out = find_my_town(corpus, "Atlantis")
    assert not out["found"]
    assert "Owen Sound" in out["message"]


# -- show_the_page -----------------------------------------------------------

def test_show_the_page_returns_a_checkable_link(corpus):
    key = corpus.records[0].key
    out = show_the_page(corpus, key)
    assert out["found"]
    assert out["page_url"].startswith("https://archive.org/details/")
    assert out["read_from"], "a claim with no quoted source is not checkable"


def test_show_the_page_on_a_bad_key_fails_clearly(corpus):
    assert show_the_page(corpus, "nope")["found"] is False


# -- read_me_the_record ------------------------------------------------------

def test_narrative_reports_direction_of_change(corpus):
    out = read_me_the_record(corpus, "Owen Sound")
    assert "Owen Sound" in out["opening"]
    bod = next(c for c in out["chapters"] if c["parameter"] == "BOD removal")
    assert bod["from"]["year"] == 1963 and bod["to"]["year"] == 1969
    assert bod["change"] == pytest.approx(64.0 - 46.4)
    assert out["how_to_check"]


def test_corpus_load_skips_non_place_reports(tmp_path):
    """gold_report / metadata_proposals have a different shape and are not
    measurements about a town."""
    (tmp_path / "gold_report.json").write_text(json.dumps({"records": [{"kind": "x"}]}))
    (tmp_path / "somewhere.json").write_text(
        json.dumps({"place": "Somewhere", "records": []})
    )
    c = Corpus.load_dir(tmp_path)
    assert c.places == ["Somewhere"]


# -- era standards -----------------------------------------------------------

def _std(year, value, parameter="BOD", unit="mg/L"):
    return Record(
        kind="standard", parameter=parameter, value=value, unit=unit,
        period=str(year), confidence=0.9,
        provenance=Provenance(identifier="id", page=3, source_text=f"limit is {value} mg/L"),
    )


@pytest.fixture
def standards():
    return Corpus(records=[_std(1965, 45), _std(1978, 25), _std(1990, 20)], places=[])


def test_standard_in_force_is_the_one_before_the_reading(standards):
    from concordance.tools import standard_for
    assert standard_for(standards, "BOD", 1969)["year"] == 1965
    assert standard_for(standards, "BOD", 1980)["year"] == 1978


def test_a_later_standard_is_flagged_not_applied(standards):
    """A limit introduced in 1978 says nothing about a 1969 discharge. Using it
    would manufacture retrospective violations."""
    from concordance.tools import standard_for
    only_later = Corpus(records=[_std(1978, 25)], places=[])
    s = standard_for(only_later, "BOD", 1969)
    assert s["applies_before_observation"] is False
    assert "AFTER the 1969 reading" in s["caveat"]


def test_judge_uses_the_era_standard_when_it_exists(standards):
    from concordance.tools import judge_reading
    out = judge_reading(standards, "BOD", 37, "mg/L", 1969)
    assert "45 mg/L limit that applied then" in out["verdict"]
    assert "caveat" not in out


def test_judge_falls_back_to_modern_and_says_so():
    from concordance.tools import judge_reading
    out = judge_reading(Corpus(records=[], places=[]), "BOD", 37, "mg/L", 1969)
    assert "modern" in out["compared_against"]
    assert "MODERN" in out["caveat"]


def test_a_standard_from_a_different_century_is_ignored(standards):
    from concordance.tools import standard_for
    assert standard_for(standards, "BOD", 1890) is None
