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


def test_one_panel_per_thing_measured_within_a_system(state: S.State) -> None:
    """"bod" appeared five times on Belleville's page: influent, effluent and
    raw, times two spellings of one plant.

    Uniqueness is per WORKS, not per town. Brantford's sewage plant and its
    drinking water supply can both measure temperature, and those are two
    different measurements of two different things -- which is exactly why the
    page is now sectioned by works.
    """
    for place, town in _towns(state):
        for system in town.get("systems") or []:
            keys = [(p["label"], p["unit"]) for p in system["panels"]]
            assert len(keys) == len(set(keys)), (
                f"{place} / {system['title']} lists a duplicate panel")


def test_a_place_page_is_sectioned_by_works(state: S.State) -> None:
    """A town's sewage plant and its water supply are different subjects, and a
    reader needs to know which a number is about before it means anything.
    Brantford interleaved 1961-1972 sewage readings with 1987-1992 drinking
    water in one flat list."""
    for place, town in _towns(state):
        systems = town.get("systems") or []
        if not (town.get("series") or []):
            continue
        assert systems, f"{place} has panels but no system grouping"
        assert sum(s["n"] for s in systems) == town["n_charted"]
        for s in systems:
            assert s["title"], f"{place} has an unnamed system"


def test_abbreviations_are_expanded_for_a_reader(state: S.State) -> None:
    """A page of ml.ss., ss and thms is unreadable to the resident this is for.

    The expansion is on the LABEL only -- the row keeps the document's own
    wording, which is what somebody checking the scan needs.
    """
    from concordance.server import plain_label

    assert plain_label("bod") == "bod (biochemical oxygen demand)"
    assert plain_label("ml.ss.").endswith("(mixed liquor suspended solids)")
    assert plain_label("bod removal").startswith("bod removal (")
    assert plain_label("hardness") == "hardness"


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
    # class, not id -- the dock and the whole-record view both render this and
    # an id can only bind the first on the page.
    assert "findbar" in page and 'class="find"' in page
    assert "record-root" in page


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


# -- shelving panels by substance -------------------------------------------

def test_panels_of_one_substance_sit_together(state: S.State) -> None:
    """Brantford listed "average daily flow", "daily flow" and "total flow" as
    three unrelated entries, and "ss" nowhere near "effluent suspended
    solids"."""
    from concordance.parameters import resolve

    for place, town in _towns(state):
        for system in town.get("systems") or []:
            runs: list[str] = []
            for panel in system["panels"]:
                got = resolve(panel["label"], panel.get("unit"))
                substance = (got.substance if got else "") or ""
                if not runs or runs[-1] != substance:
                    runs.append(substance)
            assert len(runs) == len(set(runs)), (
                f"{place} / {system['title']} splits a substance into "
                f"non-adjacent runs: {runs}")


def test_a_heading_only_appears_when_it_gathers_more_than_one(state: S.State) -> None:
    """A heading above a single panel repeating its own name is noise."""
    from concordance.parameters import resolve

    for _place, town in _towns(state):
        for system in town.get("systems") or []:
            for panel in system["panels"]:
                shelf = panel.get("shelf") or ""
                if not shelf or shelf == "everything else":
                    continue
                same = [q for q in system["panels"]
                        if ((resolve(q["label"], q.get("unit")).substance
                             if resolve(q["label"], q.get("unit")) else "") or "") == shelf]
                assert len(same) > 1, f"{shelf!r} heads only one panel"


def test_unrecognised_panels_get_their_own_divider(state: S.State) -> None:
    """Without one they sat under the previous substance's heading and read as
    though they belonged to it -- "operating costs" filed under "suspended
    solids"."""
    from concordance.parameters import resolve

    for _place, town in _towns(state):
        for system in town.get("systems") or []:
            panels = system["panels"]
            for i, panel in enumerate(panels):
                got = resolve(panel["label"], panel.get("unit"))
                if (got.substance if got else "") or "":
                    continue
                prev = panels[i - 1] if i else None
                if prev is None:
                    continue
                prev_got = resolve(prev["label"], prev.get("unit"))
                if (prev_got.substance if prev_got else "") or "":
                    assert panel.get("shelf") == "everything else", (
                        f"{panel['label']!r} follows a substance run with no divider")


def test_mixed_liquor_never_shares_an_axis_with_effluent(state: S.State) -> None:
    """They share a heading because both are suspended solids. They must not
    share a chart: MLSS runs 1,500-4,000 mg/L inside an aeration tank and
    effluent suspended solids is what leaves the plant."""
    for _place, town in _towns(state):
        for system in town.get("systems") or []:
            for panel in system["panels"]:
                label = panel["label"].lower()
                if "ml.ss" in label or "mlss" in label:
                    assert "effluent" not in label
                    assert len(panel["lines"]) >= 1
