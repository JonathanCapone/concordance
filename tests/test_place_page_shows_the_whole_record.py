"""A place page shows what that place measured, not a fixed list of parameters.

State.SERIES was seven water parameters, and it decided what EXISTED rather than
what came first. It reached 25.7% of observations. Stratford drew 4 charts out
of 66 distinct measurements; Belleville, the largest town in the corpus, drew
none at all. The owner's "I wondered how useful the data actually is being
presented this way" was a correct bug report about three quarters of the corpus
being invisible.
"""

from __future__ import annotations

import pytest

import concordance.server as S
from concordance.server import _same_town


@pytest.fixture(scope="module")
def state() -> S.State:
    return S.State()


def _pages(state: S.State):
    seen = set()
    for e in state.places:
        if not e.get("raw") or e["place"] in seen:
            continue
        seen.add(e["place"])
        town = state.town(e["place"], e["raw"])
        if town.get("found"):
            yield e, town


def _rows(town: dict) -> list[dict]:
    return [r for g in (town.get("series") or []) + (town.get("singles") or [])
            for r in g["rows"]]


def test_nearly_every_observation_is_reachable(state: S.State) -> None:
    """The measurement that matters. Was 25.7%."""
    shown = total = 0
    for e, town in _pages(state):
        want = {x for x in (e["place"].lower(), e["raw"].lower()) if x}
        total += sum(1 for r in state.corpus.records
                     if r.kind == "observation"
                     and _same_town((r.place or "").lower(), want))
        shown += len(_rows(town))
    assert total, "no observations to check"
    assert shown / total > 0.9, f"only {100*shown/total:.1f}% of observations render"


def test_no_reading_appears_twice_on_one_page(state: S.State) -> None:
    """Records land in one group each. A reading whose stream or facility
    differs between extractions used to be shown twice."""
    for _e, town in _pages(state):
        keys = [(r["parameter"], r["identifier"], r["page"], r["value"],
                 r["period"], r["unit"], r["qualifier"]) for r in _rows(town)]
        assert len(keys) == len(set(keys)), f"{town['place']} repeats a reading"


def test_a_town_shows_far_more_than_seven_parameters(state: S.State) -> None:
    """The old whitelist could never exceed seven."""
    best = max(len(t.get("series") or []) + len(t.get("singles") or [])
               for _e, t in _pages(state))
    assert best > 7, f"richest place still shows only {best} groups"


def test_a_single_reading_is_listed_not_dropped(state: S.State) -> None:
    assert any(t.get("singles") for _e, t in _pages(state))


def test_uncomparable_groups_are_listed_with_a_reason(state: S.State) -> None:
    """A group whose units cannot be reconciled still happened, and its
    readings still cite pages."""
    flagged = [g for _e, t in _pages(state)
               for g in (t.get("singles") or []) if g.get("not_comparable")]
    for g in flagged:
        assert g["rows"], "a not-comparable group must still carry its readings"


def test_every_row_carries_its_source(state: S.State) -> None:
    """The whole trust argument. A row without a page is not evidence."""
    for _e, town in _pages(state):
        for r in _rows(town):
            assert r["identifier"], f"{town['place']}: row with no identifier"
            assert "read_from" in r


def test_no_two_rows_render_identically(state: S.State) -> None:
    """A reader must be able to tell any two rows apart from what is on screen.

    Everything in the key below is displayed: the period, the page, the value,
    the unit, the qualifier and the source sentence. Two readings of one
    parameter in one year used to render as two rows both saying "1965" with
    different numbers and nothing to distinguish them, which is why the page is
    now printed beside the year.

    Rows sharing a period, page and value but carrying different sentences are
    legitimate and stay: they come from different volumes, and one of them may
    be wrong. Surfacing that is the dispute ledger's job, not a reason to hide
    either reading.
    """
    for _e, town in _pages(state):
        for g in (town.get("series") or []) + (town.get("singles") or []):
            shown = [(r["period"], r["page"], r["value"], r["unit"],
                      r["qualifier"], r["read_from"]) for r in g["rows"]]
            assert len(shown) == len(set(shown)), (
                f"{town['place']} / {g['label']} renders two identical rows")
