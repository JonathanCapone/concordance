"""A place page a person can actually use.

Showing everything fixed the previous bug and created this one: Belleville's
page rendered 185 groups and 448 readings in one flat run, with "bod" appearing
five times. Visible is not the same as usable.

Three things make it navigable, and each is a property rather than a style
choice: one panel per thing measured, the streams of that thing on one chart,
and the readings folded away until asked for.
"""

from __future__ import annotations

import pytest

import concordance.server as S


@pytest.fixture(scope="module")
def state() -> S.State:
    return S.State()


def _towns(state: S.State):
    seen = set()
    for e in state.places:
        if not e.get("raw") or e["place"] in seen:
            continue
        seen.add(e["place"])
        t = state.town(e["place"], e["raw"])
        if t.get("found"):
            yield e["place"], t


def test_one_panel_per_thing_measured(state: S.State) -> None:
    """"bod" appeared five times on Belleville's page: influent, effluent and
    raw, times two spellings of one plant."""
    for place, town in _towns(state):
        labels = [p["label"] for p in town.get("series") or []]
        assert len(labels) == len(set(labels)), (
            f"{place} lists {len(labels)-len(set(labels))} duplicate panels")


def test_streams_are_lines_in_one_panel_not_separate_panels(state: S.State) -> None:
    """Influent against effluent on one axis is the question this archive
    answers. It should appear at least once in the real data."""
    multi = [p for _pl, t in _towns(state)
             for p in (t.get("series") or []) if len(p["lines"]) > 1]
    assert multi, "no panel anywhere puts two streams on one chart"
    for p in multi:
        names = [l["name"] for l in p["lines"]]
        assert len(names) == len(set(names)), f"{p['label']} has two lines named alike"
        assert "unknown" not in names


def test_a_line_is_named_only_by_what_distinguishes_it(state: S.State) -> None:
    """Repeating one plant's name on every line of a single-plant panel, or
    printing "unknown" for a stream nobody recorded, makes a legend
    unreadable."""
    for _place, town in _towns(state):
        for p in town.get("series") or []:
            if len(p["lines"]) == 1:
                assert p["lines"][0]["name"] == "reported"


def test_the_page_collapses_instead_of_dumping(state: S.State) -> None:
    page = state.html()
    assert '<details class="panel' in page
    assert "findbar" in page and 'id="find"' in page


def test_a_panel_carries_enough_to_scan_without_opening(state: S.State) -> None:
    """Span, range and count, so a reader can choose what to open."""
    for _place, town in _towns(state):
        for p in town.get("series") or []:
            assert p["n"] >= 1
            assert p["span"] and len(p["span"]) == 2
            assert p["range"] and len(p["range"]) == 2
            assert p["span"][0] <= p["span"][1]


def test_grouping_did_not_lose_any_reading(state: S.State) -> None:
    """The whole point of the previous change was that nothing disappears."""
    for place, town in _towns(state):
        in_panels = sum(p["n"] for p in town.get("series") or [])
        in_singles = sum(len(g["rows"]) for g in town.get("singles") or [])
        in_other = sum(len(g["rows"]) for g in town.get("other") or [])
        assert in_panels == town["n_charted"], f"{place}: panel count disagrees"
        # Orangeville has 22 records and not one observation -- every reading
        # about it is a design specification -- so a page can legitimately have
        # no charts and must still show something.
        assert in_panels + in_singles + in_other > 0, f"{place} renders nothing"


def test_design_figures_and_limits_are_shown_but_never_charted(state: S.State) -> None:
    """A design capacity plotted as a measurement is the clean, plausible,
    entirely fictional trend this project exists to avoid. Hiding it is the
    other failure: "what it was built for" is exactly what a reader wants
    beside what it actually did."""
    seen_any = False
    for place, town in _towns(state):
        for g in town.get("other") or []:
            seen_any = True
            assert g["kind"] != "observation"
            assert g["rows"], f"{place}: empty {g['kind']} group"
            for r in g["rows"]:
                assert r["charted"] is False
    assert seen_any, "no place surfaces a design figure or a standard"


def test_two_plants_in_one_town_stay_apart(state: S.State) -> None:
    """Burlington has Drury Lane and Elizabeth Gardens. A sewage plant and a
    water works measure opposite things and must never share a chart."""
    from concordance.places import facility_key

    a = facility_key("Burlington Drury Lane Water Pollution Control Plant", "Burlington")
    b = facility_key("Burlington Elizabeth Gardens Water Pollution Control Plant",
                     "Burlington")
    assert a != b
    # ...while two spellings of one plant merge.
    assert (facility_key("Belleville water pollution control plant", "Belleville")
            == facility_key("water pollution control plant", "Belleville"))
