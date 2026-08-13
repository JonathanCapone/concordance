"""Tests for the vocabulary-coverage measurement.

This module exists to decide when to stop paying for a sampling run, so the
failures that matter are the ones that make it stop too early with a confident
number. Every test here corresponds to a way the figure could be bought rather
than earned.
"""

from __future__ import annotations

from concordance.vocab_sample import (
    Coverage, Reading, Survey, allocate, contradicted, plan, stratify,
    stratum_of,
)


def _reading(param, unit=None, quote="", stratum="s1", family="f1"):
    return Reading(parameter=param, unit=unit, source_text=quote,
                   stratum=stratum, family=family)


# -- the estimator ----------------------------------------------------------

def test_miss_rate_is_the_share_of_terms_seen_once():
    """Good-Turing: the singletons are the estimate of what is still unseen."""
    c = Coverage(readings=100, observed=30, singletons=5, doubletons=8)
    assert c.miss_rate == 0.05
    assert c.coverage == 0.95


def test_chao1_survives_having_seen_nothing_twice():
    """Early in a run f2 is routinely zero, and the uncorrected form divides
    by it. A richness estimate that raises ZeroDivisionError on round one is
    a stopping rule that cannot start."""
    c = Coverage(readings=10, observed=10, singletons=10, doubletons=0)
    assert c.chao1 == 10 + (10 * 9) / 2
    lo, hi = c.chao1_ci95
    assert lo <= c.chao1 <= hi


def test_too_few_readings_is_reported_as_unjudged_not_as_covered():
    assert not Coverage(readings=3, observed=3, singletons=0, doubletons=0).judged


# -- the circularity control ------------------------------------------------

def test_a_name_the_page_did_not_use_is_not_the_archive_speaking():
    """17.2% of real parameter names are absent from their own source sentence.

    "It is retained in the clarifiers for 2 hours" yields `retention time`; the
    page never says those words. That is correct interpretation, but the model's
    naming habits are few and saturate at once, so counting them as archive
    vocabulary flattens the curve on the prompt rather than on the corpus.
    """
    s = Survey()
    s.observe([_reading("retention time", "hours",
                        "It is retained in the clarifiers for 2 hours.")])
    s.observe([_reading("suspended solids", "mg/L",
                        "The average suspended solids were 224 mg/1.")])

    assert [t.stem for t in s.archive_terms()] == ["suspended solids"]
    assert [t.stem for t in s.model_terms()] == ["retention time"]
    assert s.coverage(archive_only=True).observed == 1


def test_the_stopping_rule_ignores_the_model_population():
    s = Survey()
    # A hundred readings the model named, all the same way: perfect apparent
    # coverage that says nothing about the archive.
    s.observe([_reading("diameter", "feet", "the tank is 70 feet across")] * 100)
    assert not s.done()


# -- the ratchet ------------------------------------------------------------

def test_a_measure_its_own_unit_denies_is_a_miss_not_a_hit():
    """Otherwise the rule is a ratchet: accept enough proposals and any target
    is met, whether or not one mapping is right. BOD in pounds and BOD in mg/L
    resolve to the same identity today."""
    assert contradicted("concentration", "pounds")
    assert not contradicted("concentration", "mg/L")
    assert contradicted("total", "million gallons per day")
    assert not contradicted("total", "million gallons")

    # The example this was written from -- BOD in pounds resolving to a
    # CONCENTRATION -- no longer happens: `parameters` now reads a bare mass as
    # a total, so resolve() gets it right and there is nothing left to contest.
    # That is the better outcome, and it means the survey's guard has to be
    # exercised on a contradiction the resolver can still produce rather than on
    # one that has been fixed underneath it.
    from concordance.parameters import resolve

    assert resolve("BOD", "pounds").measure == "total"

    s = Survey()
    s.observe([_reading("chlorine dosage", "gallons per day",
                        "the chlorine dosage was 3 gallons per day")])
    term = next(iter(s.terms.values()))
    assert term.resolved
    if term.contested:
        assert not term.settled
        assert term in s.unsettled_terms()


# -- identity ---------------------------------------------------------------

def test_one_stem_can_be_two_measurements():
    """Nine of 155 stems span more than one canonical identity. The stem 'flow'
    covers a rate, a removal and a total; merging them is the defect that put
    removal percentages on a concentration axis."""
    s = Survey()
    s.observe([
        _reading("average daily flow", "million gallons per day",
                 "the average daily flow was 5.7 million gallons per day"),
        _reading("total flow", "million gallons",
                 "the total flow was 176.5 million gallons"),
    ])
    assert len(s.terms) == 2
    assert {t.measure for t in s.terms.values()} == {"rate", "total"}


# -- strata -----------------------------------------------------------------

def test_a_pooled_figure_cannot_hide_an_untouched_corner():
    """Coverage can read 97% overall while an agency is entirely unsampled."""
    s = Survey()
    s.strata_planned = {"big": 500, "small": 20}
    s.observe([_reading(f"term {i}", "mg/L", f"the term {i} was 5 mg/L",
                        stratum="big") for i in range(80)] * 3)
    s.observe([_reading("something", "mg/L", "the something was 5 mg/L",
                        stratum="small")])
    assert "small" in s.unjudged_strata()
    assert not s.done()


def test_generic_collections_cannot_be_strata():
    assert stratum_of({"collection": ["governmentpublications", "toronto"]}) == "unsorted"
    assert stratum_of({"collection": ["toronto", "statisticscanada"]}) == "statisticscanada"


def test_items_land_in_their_rarest_collection():
    """Otherwise an item goes wherever the metadata happened to list first,
    which put 51,137 items in one bucket and left another with three."""
    index = [{"identifier": "a", "collection": ["uoftgovpubs", "rare"]}] + [
        {"identifier": f"b{i}", "collection": ["uoftgovpubs"]} for i in range(20)]
    grouped = stratify(index)
    assert [it["identifier"] for it in grouped["rare"]] == ["a"]
    assert len(grouped["uoftgovpubs"]) == 20


def test_allocation_favours_breadth_over_the_biggest_collection():
    """Proportional allocation gives U of T half of every run and never reaches
    forestry. Square-root allocation turns a 511:1 ratio into 22:1."""
    got = allocate({"huge": 51137, "small": 100}, budget=1000)
    ratio = got["huge"] / got["small"]
    assert 15 < ratio < 30
    assert sum(got.values()) <= 1000


def test_no_stratum_is_silently_dropped():
    got = allocate({"huge": 90000, "tiny": 3}, budget=500, floor=2)
    assert got["tiny"] >= 2


def test_a_plan_is_reproducible():
    index = [{"identifier": f"i{i}", "collection": ["x"], "title": "t"} for i in range(50)]
    a = plan(index, budget=100, seed=7)
    b = plan(index, budget=100, seed=7)
    assert [p.identifier for p in a.picks] == [p.identifier for p in b.picks]


def test_a_plan_spreads_across_documents_rather_than_down_one():
    """A document's later pages repeat its earlier vocabulary, so breadth beats
    depth per page spent."""
    index = [{"identifier": f"i{i}", "collection": ["x"], "title": "t"} for i in range(50)]
    p = plan(index, budget=100, seed=1, page_cap=10)
    assert len(p.picks) >= 10
    assert max(pick.pages for pick in p.picks) <= 10


# -- honesty ----------------------------------------------------------------

def test_the_report_says_what_it_did_not_measure():
    s = Survey()
    s.observe([_reading("BOD", "mg/L", "the BOD was 104 mg/1")])
    report = s.report()
    assert report["not_measured"]
    assert any("TABLE" in n for n in report["not_measured"])
    assert "model_language" in report and "archive_language" in report
