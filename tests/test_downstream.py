"""Tests for upstream/downstream influence.

This is the easiest place in the project to fool yourself. Two towns on one
river share weather, share a growing population, share the decade's industry --
their numbers move together whether or not one affects the other. So the tests
are weighted toward the refusals and the caveats, not the correlation.
"""

from __future__ import annotations

import pytest

from concordance.downstream import MIN_OVERLAP, spearman, upstream_influence
from concordance.models import Provenance, Record


def _rec(year, value, stream, parameter="BOD", unit="mg/L"):
    return Record(
        kind="observation", parameter=parameter, value=value, unit=unit,
        stream=stream, period=str(year), confidence=0.9,
        provenance=Provenance(identifier="x", page=1, source_text="s"),
    )


# -- spearman ----------------------------------------------------------------

def test_spearman_is_rank_based_not_linear():
    """Monotonic but wildly non-linear data must still score 1.0 -- six OCR'd
    readings cannot support an assumption of linearity."""
    assert spearman([1, 2, 3, 4], [1, 10, 1000, 100000]) == pytest.approx(1.0)


def test_spearman_handles_inversion():
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)


def test_spearman_refuses_tiny_input():
    assert spearman([1, 2], [1, 2]) is None


# -- the refusals ------------------------------------------------------------

def test_short_overlap_is_refused_not_hedged():
    """Four points correlate by accident often enough that quoting a number
    would mislead however carefully it is worded."""
    up = [_rec(y, 30 + y % 5, "effluent") for y in range(1963, 1967)]
    down = [_rec(y, 100 + y % 5, "influent") for y in range(1963, 1967)]
    out = upstream_influence(up, down, upstream_place="A", downstream_place="B")
    assert not out.reportable
    assert out.correlation is None
    assert "minimum" in out.reason


def test_no_shared_years_is_refused():
    up = [_rec(y, 30, "effluent") for y in range(1960, 1966)]
    down = [_rec(y, 100, "influent") for y in range(1980, 1986)]
    out = upstream_influence(up, down, upstream_place="A", downstream_place="B")
    assert not out.reportable
    assert out.years == []


def test_flat_series_gives_no_correlation():
    up = [_rec(y, 30, "effluent") for y in range(1960, 1967)]
    down = [_rec(y, 100, "influent") for y in range(1960, 1967)]
    out = upstream_influence(up, down, upstream_place="A", downstream_place="B")
    assert not out.reportable
    assert "undefined" in out.reason


# -- the comparison itself ---------------------------------------------------

def test_it_pairs_effluent_upstream_with_influent_downstream():
    """Comparing two effluents would only show that both towns were growing.
    What matters is what the lower town RECEIVED."""
    years = range(1960, 1967)
    up = ([_rec(y, 20 + i * 5, "effluent") for i, y in enumerate(years)]
          + [_rec(y, 999, "influent") for y in years])          # must be ignored
    down = ([_rec(y, 60 + i * 5, "influent") for i, y in enumerate(years)]
            + [_rec(y, 111, "effluent") for y in years])        # must be ignored
    out = upstream_influence(up, down, upstream_place="A", downstream_place="B")
    assert out.reportable
    assert 999 not in out.upstream_values
    assert 111 not in out.downstream_values
    assert out.correlation == pytest.approx(1.0)


def test_result_carries_its_confounders():
    """A reader must see why the number is weak at the same moment they see it."""
    years = range(1960, 1967)
    up = [_rec(y, 20 + i * 3, "effluent") for i, y in enumerate(years)]
    down = [_rec(y, 60 + i * 2, "influent") for i, y in enumerate(years)]
    out = upstream_influence(up, down, upstream_place="A", downstream_place="B")
    assert out.reportable
    joined = " ".join(out.confounders)
    assert "weather" in joined and "dilution" in joined


def test_description_never_claims_causation():
    years = range(1960, 1967)
    up = [_rec(y, 20 + i * 3, "effluent") for i, y in enumerate(years)]
    down = [_rec(y, 60 + i * 2, "influent") for i, y in enumerate(years)]
    text = upstream_influence(
        up, down, upstream_place="A", downstream_place="B"
    ).describe().lower()
    assert "caus" not in text
    assert "not evidence of effect" in text


def test_min_overlap_is_at_least_five():
    assert MIN_OVERLAP >= 5
