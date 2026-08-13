"""Tests for parameter resolution.

Every case here comes from the Owen Sound series, where substring matching put
removal percentages into the effluent-concentration chart. That failure is the
dangerous kind: a removal percentage and a concentration are both small positive
numbers that fall when a plant improves, so the chart looked entirely reasonable.
"""

from __future__ import annotations

import pytest

from concordance.parameters import resolve, same_measurement


@pytest.mark.parametrize(
    ("name", "unit", "key"),
    [
        ("BOD", "mg/L", "bod|concentration"),
        ("Five Day BOD", "PPM", "bod|concentration"),
        ("BOD removal", "%", "bod|removal"),
        ("biochemical oxygen demand removal", "%", "bod|removal"),
        ("suspended solids", "mg/L", "suspended solids|concentration"),
        ("suspended solids removal", "%", "suspended solids|removal"),
        ("daily flow", "million gallons per day", "flow|rate"),
        ("total flow", "million gallons", "flow|total"),
        ("Design Plant Flow", "MGD", "flow|capacity"),
        ("Design Population", "persons", "population|capacity"),
    ],
)
def test_resolves_to_canonical_key(name, unit, key):
    p = resolve(name, unit)
    assert p is not None and p.key == key


# -- synonyms must merge -----------------------------------------------------

@pytest.mark.parametrize(
    ("a", "au", "b", "bu"),
    [
        ("BOD removal", "%", "biochemical oxygen demand removal", "%"),
        ("Five Day BOD", "PPM", "BOD", "mg/1"),
        ("S.S.", "mg/L", "suspended solids", "mg/L"),
    ],
)
def test_synonyms_merge(a, au, b, bu):
    assert same_measurement(a, au, b, bu)


# -- distinct measurements must NOT merge ------------------------------------

@pytest.mark.parametrize(
    ("a", "au", "b", "bu", "why"),
    [
        ("BOD", "mg/L", "BOD removal", "%",
         "a concentration and a percentage are not one series"),
        ("suspended solids", "mg/L", "suspended solids removal", "%",
         "the exact conflation that corrupted the effluent chart"),
        ("daily flow", "MGD", "total flow", "million gallons",
         "a rate and a yearly volume are different quantities"),
        ("Design Plant Flow", "MGD", "daily flow", "MGD",
         "engineered capacity is not a measurement"),
    ],
)
def test_distinct_measurements_do_not_merge(a, au, b, bu, why):
    assert not same_measurement(a, au, b, bu), why


# -- the unit overrules the wording ------------------------------------------

def test_unit_of_percent_forces_removal_even_when_name_says_otherwise():
    """A value in % is not a concentration whatever the label claims."""
    assert resolve("BOD", "%").measure == "removal"


def test_unrecognised_substance_returns_none():
    assert resolve("widget throughput", "each") is None


def test_unrecognised_names_fall_back_to_exact_equality_not_overlap():
    """Two unknown names must not merge just because they share a word.

    Guessing here is what produced the original bug, so the fallback is strict.
    """
    assert not same_measurement("widget alpha", None, "widget beta", None)
    assert same_measurement("widget alpha", None, "Widget Alpha", None)


def test_empty_name_is_not_a_parameter():
    assert resolve("", "mg/L") is None


# -- exceedance frequency is not removal -------------------------------------

def test_exceedance_frequency_is_not_removal():
    """Brantford 1962: "the Commission's objective for BOD was exceeded only
    20 per cent of the time" was filed as "BOD removal 20%".

    Both are percentages so the unit cannot separate them, and the meaning
    inverts: 20% exceedance is a good year, 20% removal is a failing plant.
    """
    assert resolve("BOD exceeded 20 per cent of the time", "%").key == "bod|frequency"
    assert resolve("BOD exceedance frequency", "%").key == "bod|frequency"
    assert not same_measurement("BOD removal", "%", "BOD exceedance frequency", "%")


def test_genuine_removal_still_resolves_as_removal():
    assert resolve("BOD removal", "%").key == "bod|removal"
    assert resolve("suspended solids removal", "%").key == "suspended solids|removal"


def test_vocabulary_edits_take_effect_only_after_rebuild():
    """The match order is a snapshot, and forgetting that ends a run early.

    The vocabulary is meant to be built in rounds -- sample, harvest what did
    not resolve, accept proposals, measure the improvement, sample again. The
    ordered term list is bound at import, so a round that accepts new terms and
    re-scores without rebuilding measures the previous round's table and reports
    a marginal gain of exactly zero. Every stratum would then hit its stopping
    rule simultaneously, on evidence that was an artefact of import order.
    """
    import concordance.parameters as P

    original = list(P.VOCABULARY.get("forestry", []))
    try:
        assert P.resolve("cordwood cut", "cords") is not None
        P.VOCABULARY.setdefault("forestry", []).append(("cordwood", "cordwood"))
        assert P.resolve("cordwood cut", "cords").substance != "cordwood"
        P.rebuild()
        assert P.resolve("cordwood cut", "cords").substance == "cordwood"
    finally:
        P.VOCABULARY["forestry"] = original
        P.rebuild()


# -- one name, several quantities -------------------------------------------

def test_a_ratio_measures_its_numerator():
    """Brantford's BOD-removal chart plotted an air-supply ratio.

    "CUBIC FEET AIR PER LB BOD. REMOVED" resolved to bod/removal on the strength
    of the word BOD, and its twelve monthly readings around 1,200 outnumbered
    the two real removal percentages -- so the series was published in cubic
    feet and the portal showed "BOD removal · % = 1149".

    The denominator of a ratio is what the number is normalised BY. It is never
    what the number measures.
    """
    from concordance.parameters import resolve

    assert resolve("CUBIC FEET AIR PER LB BOD. REMOVED", "cubic feet") is None
    assert resolve("cost per pound of suspended solids removed", "$").substance == "cost"


def test_a_qualifier_is_not_a_denominator():
    """"per capita" and "per month" say what kind of number it is, not what of.

    Stripping them lost "Daily Per Capita Flow" entirely, because there the
    qualifier sits in front of the substance rather than after it.
    """
    from concordance.parameters import resolve

    assert resolve("Daily Per Capita Flow", "gallons").key == "flow|rate"
    assert resolve("chlorine used per month", "pounds").substance == "chlorine"


def test_a_mass_removed_is_not_a_removal_efficiency():
    """"A total of 2,398.4 tons of BOD was removed" and "BOD removal efficiency
    was 94%" both say removal, and are a mass and a ratio. Sharing an identity,
    three tonnages outvoted three percentages and the chart was published in
    tonnes."""
    from concordance.parameters import resolve

    assert resolve("BOD removed", "tons").measure == "total"
    assert resolve("BOD removal efficiency", "%").measure == "removal"


def test_a_bare_volume_does_not_override_an_explicit_rate():
    """"Daily flow: 6.12 million gallons" carries its rate in the wording.

    Letting the unit win moved a day's flow into the annual series.
    """
    from concordance.parameters import resolve

    assert resolve("daily flow", "million gallons").key == "flow|rate"
    assert resolve("total flow", "million gallons").key == "flow|total"


def test_an_exceedance_is_never_a_removal():
    """20% exceedance is a good year; 20% removal is a failing plant.

    "exceeded" was already caught. "exceeding" and "objectives met" were the
    spellings that slipped past, and Brantford's 1962 exceedance reached the
    live chart as BOD removal.
    """
    from concordance.parameters import resolve

    assert resolve("BOD exceeding objective", "percent").measure == "frequency"
    assert resolve("BOD objectives met", "percent").measure == "frequency"
    assert resolve("BOD removal efficiency", "%").measure == "removal"
