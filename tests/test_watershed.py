"""Tests for the downstream network.

The output of this module is a claim about whose sewage reached whose drinking
water. That is the most consequential thing the project says, and it is built on
an approximation, so the tests are weighted toward the ways it can be confidently
wrong rather than the ways it can crash.
"""

from __future__ import annotations

import pytest

from groundtruth.watershed import (
    MAX_RIVER_SPREAD_KM,
    PlacedPlant,
    Station,
    downstream_links,
    haversine_km,
    place_plants,
    watercourse_of,
    who_was_upstream,
)


# -- reading the river out of a gauge name -----------------------------------

@pytest.mark.parametrize(
    ("station", "river"),
    [
        ("KAMINISTIQUIA RIVER AT MOKOMON", "kaministiquia river"),
        ("PINE RIVER NEAR CROOKS", "pine river"),
        ("GRAND RIVER ABOVE BRANTFORD", "grand river"),
        ("THAMES RIVER BELOW CHATHAM", "thames river"),
        ("SPEED RIVER AT OUTLET OF GUELPH LAKE", "speed river"),
        ("DAAQUAM (RIVIERE) EN AVAL DE LA RIVIERE SHIDGEL", "daaquam riviere"),
    ],
)
def test_watercourse_is_extracted_without_the_locator(station, river):
    assert watercourse_of(station) == river


def test_a_gauge_with_no_watercourse_is_not_guessed():
    """A lake or reservoir gauge has no downstream ordering in this scheme."""
    assert watercourse_of("LAKE ERIE AT PORT COLBORNE") is None
    assert watercourse_of("") is None


# -- the failure this module is most likely to make --------------------------

def _station(name, lat, lon, da):
    return Station(
        identifier=name[:4], name=name, lat=lat, lon=lon,
        drainage_area_km2=da, watercourse=watercourse_of(name),
    )


def test_two_rivers_sharing_a_name_are_not_linked():
    """Ontario has two Sydenham Rivers -- one draining to Georgian Bay at Owen
    Sound, one to Lake St. Clair at Wallaceburg, in unconnected watersheds.

    An earlier 300 km threshold linked them and produced a confident, wrong claim
    about whose effluent reached whose water. Their gauges are 244 km apart.
    """
    plants = [
        PlacedPlant("Owen Sound", 44.57, -80.93,
                    _station("SYDENHAM RIVER NEAR OWEN SOUND", 44.57, -80.93, 250)),
        PlacedPlant("Wallaceburg", 42.60, -82.39,
                    _station("SYDENHAM RIVER NEAR WALLACEBURG", 42.60, -82.39, 2700)),
    ]
    links, warnings = downstream_links(plants)
    assert links == [], "must not link two rivers that merely share a name"
    assert any("sydenham" in w for w in warnings), "the exclusion must be reported"


def test_a_real_long_river_is_still_linked():
    """The Thames spans 127 km of gauges legitimately, and must survive the
    threshold that excludes the Sydenham at 244 km."""
    plants = [
        PlacedPlant("Ingersoll", 43.04, -80.88,
                    _station("THAMES RIVER AT INGERSOLL", 43.04, -80.88, 500)),
        PlacedPlant("Chatham", 42.40, -82.19,
                    _station("THAMES RIVER AT CHATHAM", 42.40, -82.19, 4300)),
    ]
    links, _ = downstream_links(plants)
    assert [(l.upstream, l.downstream) for l in links] == [("Ingersoll", "Chatham")]


def test_threshold_sits_between_the_observed_cases():
    """127 km (Thames, real) < threshold < 244 km (Sydenham, false)."""
    assert 127 < MAX_RIVER_SPREAD_KM < 244


# -- ordering ----------------------------------------------------------------

def test_downstream_order_follows_catchment_area():
    """Drainage area necessarily increases downstream, which is what makes this
    orderable without a routed network."""
    plants = [
        PlacedPlant("Cayuga", 42.95, -79.86, _station("GRAND RIVER AT CAYUGA", 42.95, -79.86, 5210)),
        PlacedPlant("Fergus", 43.70, -80.37, _station("GRAND RIVER AT FERGUS", 43.70, -80.37, 1120)),
        PlacedPlant("Brantford", 43.14, -80.26, _station("GRAND RIVER AT BRANTFORD", 43.14, -80.26, 4300)),
    ]
    links, _ = downstream_links(plants)
    assert [(l.upstream, l.downstream) for l in links] == [
        ("Fergus", "Brantford"), ("Brantford", "Cayuga")
    ]


def test_upstream_is_transitive():
    plants = [
        PlacedPlant("Cayuga", 42.95, -79.86, _station("GRAND RIVER AT CAYUGA", 42.95, -79.86, 5210)),
        PlacedPlant("Fergus", 43.70, -80.37, _station("GRAND RIVER AT FERGUS", 43.70, -80.37, 1120)),
        PlacedPlant("Brantford", 43.14, -80.26, _station("GRAND RIVER AT BRANTFORD", 43.14, -80.26, 4300)),
    ]
    links, _ = downstream_links(plants)
    upstream = {u["place"] for u in who_was_upstream(links, "Cayuga")}
    assert upstream == {"Brantford", "Fergus"}


def test_every_link_carries_its_caveat():
    """This is an inference about a real community's water and must never be
    handed on as established fact."""
    plants = [
        PlacedPlant("A", 43.7, -80.37, _station("GRAND RIVER AT A", 43.7, -80.37, 1120)),
        PlacedPlant("B", 43.14, -80.26, _station("GRAND RIVER AT B", 43.14, -80.26, 4300)),
    ]
    links, _ = downstream_links(plants)
    assert links and "National Hydro Network" in links[0].caveat
    assert all("caveat" in u for u in who_was_upstream(links, "B"))


# -- deduplication -----------------------------------------------------------

def test_one_town_recorded_three_ways_becomes_one_plant():
    """The corpus lists 'Sidney Township (Batawa)', 'Sidney Twp.- (Batawa)' and
    'Sidney (Batawa)'. Treating them as three plants invents upstream links
    between a place and itself."""
    st = [_station("TRENT RIVER AT BATAWA", 44.18, -77.58, 12000)]
    plants = [
        ("Sidney Township (Batawa)", 44.18, -77.58),
        ("Sidney Twp.- (Batawa)", 44.18, -77.58),
        ("Sidney (Batawa)", 44.18, -77.58),
    ]
    assert len(place_plants(plants, st)) == 1


def test_distant_plants_are_not_placed_on_a_faraway_gauge():
    st = [_station("GRAND RIVER AT BRANTFORD", 43.14, -80.26, 4300)]
    [p] = place_plants([("Thunder Bay", 48.40, -89.27)], st)
    assert p.station is None and p.confidence == "not placed"


def test_haversine_is_sane():
    # Toronto to Ottawa, roughly 350 km
    assert 330 < haversine_km(43.65, -79.38, 45.42, -75.70) < 370
