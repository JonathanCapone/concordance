"""Tests for the methods-drift layer.

The refusals matter as much as the conversions. A unit layer that silently
coerces produces a smooth, confident, fictional trend -- which is worse than an
error, because nothing about it looks wrong.
"""

from __future__ import annotations

import pytest

from groundtruth.units import (
    IMPERIAL_TO_US,
    comparable,
    normalize_series,
    parse_unit,
    to_base,
)


# -- the actual corpus cases -------------------------------------------------

def test_ppm_and_mg_per_litre_reconcile():
    """Owen Sound's design BOD is '180 PPM' in 1963 and '180 mg/1' in 1969.

    Same plant, same specification, six years apart. If these don't reconcile the
    plant appears to have changed when only the typist did.
    """
    a = to_base(180, "PPM", era=1963)
    b = to_base(180, "mg/1", era=1969)
    assert a.value == b.value == 180.0
    assert a.unit == b.unit == "mg/l"
    ok, _ = comparable(a, b)
    assert ok


def test_ppm_conversion_records_its_assumption():
    """1 ppm == 1 mg/L holds for dilute aqueous samples, not universally."""
    q = to_base(180, "ppm")
    assert q.assumptions
    assert not q.is_safe


def test_ocr_mangled_mg_per_litre_is_understood():
    """OCR renders 'mg/L' as 'mg/1' and sometimes 'mg/i'."""
    for spelling in ("mg/1", "mg/l", "mg/L", "mg / 1"):
        assert to_base(104, spelling).unit == "mg/l"


# -- Imperial gallons --------------------------------------------------------

def test_imperial_gallons_are_converted():
    """A 20% error hiding in every flow figure in the corpus."""
    q = to_base(1.0, "million Imperial gallons per day", era=1963)
    assert q.unit == "gal/day"
    assert q.value == pytest.approx(1e6 * IMPERIAL_TO_US)
    assert q.assumptions


def test_mgd_in_a_canadian_report_is_imperial():
    imperial = to_base(3.0, "million Imperial gallons per day", era=1963)
    mgd = to_base(3.0, "MGD", era=1969)
    assert mgd.value == pytest.approx(imperial.value)
    assert any("Imperial" in a for a in mgd.assumptions)


def test_bare_gallons_before_metrication_is_flagged_not_converted():
    """Probably Imperial -- but 'probably' is not grounds for changing a number."""
    q = to_base(1000, "gallons", era=1969)
    assert q.value == 1000, "must not silently apply a conversion it isn't sure of"
    assert any("probably Imperial" in a for a in q.assumptions)


# -- refusals ----------------------------------------------------------------

def test_concentration_and_mass_rate_are_incommensurable():
    """BOD as mg/L and BOD as lb/day are different physical quantities.

    Converting needs the flow. Guessing turns a plant that improved into one that
    got worse.
    """
    ok, why = comparable(to_base(104, "mg/L"), to_base(2600, "lb/day"))
    assert not ok
    assert "concentration" in why and "mass_rate" in why


def test_unrecognised_unit_is_refused_not_guessed():
    assert parse_unit("furlongs per fortnight") is None
    ok, why = comparable(to_base(1, "mg/L"), to_base(1, "furlongs per fortnight"))
    assert not ok
    assert "not recognised" in why


def test_percent_is_not_a_concentration():
    ok, _ = comparable(to_base(64, "%"), to_base(64, "mg/L"))
    assert not ok


# -- series ------------------------------------------------------------------

def test_series_rejects_the_odd_unit_rather_than_coercing_it():
    points = [
        (1963, 180, "PPM", 0.9),
        (1965, 175, "mg/1", 0.9),
        (1967, 160, "mg/L", 0.9),
        (1969, 150, "mg/1", 0.9),
        (1971, 2600, "lb/day", 0.9),   # a reporting-method change, not a reading
    ]
    kept, assumptions, rejected = normalize_series(points)
    assert [int(y) for y, _, _ in kept] == [1963, 1965, 1967, 1969]
    assert len(rejected) == 1 and "1971" in rejected[0]
    assert assumptions, "the ppm assumption must reach the caller"


def test_series_surfaces_unrecognised_units_as_rejections():
    kept, _, rejected = normalize_series([(1970, 5, "sploops", 0.9), (1971, 6, "mg/L", 0.9)])
    assert len(kept) == 1
    assert any("sploops" in r for r in rejected)


def test_empty_series_is_not_an_error():
    assert normalize_series([]) == ([], [], [])
