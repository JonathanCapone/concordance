"""Tests for the frontier.

The property that matters is honesty about distance. A frontier that flatters
the reader -- rounding four documents down to "nearly there" -- is worse than no
frontier, because someone spends an hour on the strength of it.
"""

from __future__ import annotations

from dataclasses import dataclass

from groundtruth.frontier import build


@dataclass
class Link:
    upstream: str
    downstream: str
    watercourse: str


def _record(place, year=1969):
    return {"place": place, "period": str(year), "parameter": "BOD", "value": 10}


def test_a_comparison_needing_two_towns_is_not_half_answered():
    """Reading one of two required towns does not make the question 50% done.
    It is still unanswerable, and now one document away."""
    f = build([_record("Brantford")],
              downstream_links=[Link("Fergus", "Brantford", "grand river")])
    q = next(q for q in f.questions if q.kind == "downstream")
    assert not q.answerable
    assert q.distance == 1 and q.needs == ["Fergus"] and q.have == ["Brantford"]


def test_reading_both_towns_makes_it_answerable():
    f = build([_record("Fergus"), _record("Brantford")],
              downstream_links=[Link("Fergus", "Brantford", "grand river")])
    assert f.questions[0].answerable


def test_unlocks_names_exactly_what_an_hour_buys():
    f = build([_record("Brantford")],
              downstream_links=[Link("Fergus", "Brantford", "grand river")])
    assert [q.kind for q in f.unlocks("Fergus")] == ["downstream"]
    assert f.unlocks("Cayuga") == []


def test_distance_is_not_flattered():
    """A whole-river question needing three unread towns says three."""
    f = build([], downstream_links=[
        Link("A", "B", "r"), Link("B", "C", "r"),
    ])
    river = next(q for q in f.questions if q.kind == "river")
    assert river.distance == 3


def test_a_town_on_several_questions_outranks_one_on_a_distant_question():
    f = build([_record("Brantford")], downstream_links=[
        Link("Fergus", "Brantford", "grand river"),
        Link("Brantford", "Cayuga", "grand river"),
    ], coverage={"Fergus": list(range(1964, 1975))})
    ranked = {r["place"]: r["score"] for r in f.ranked_places()}
    assert ranked["Fergus"] > ranked["Cayuga"]


def test_a_trend_is_not_promised_below_the_statistical_minimum():
    """science.trend() refuses under six years. A frontier promising a trend the
    statistics layer will then decline to compute would be lying."""
    f = build([], coverage={"Tiny": [1969, 1970]})
    assert not [q for q in f.questions if q.kind == "trend"]


def test_an_already_read_town_with_enough_years_is_answerable_now():
    recs = [_record("Owen Sound", y) for y in range(1963, 1971)]
    f = build(recs, coverage={"Owen Sound": list(range(1963, 1971))})
    trend = next(q for q in f.questions if q.kind == "trend")
    assert trend.answerable


def test_the_decisions_behind_a_town_s_numbers_are_a_question_too():
    """The archive's strongest unasked question, and the cheapest to close.

    A plant's numbers say what happened. The same town's council minutes say who
    voted to build it and what they were told. Both are in this collection and
    they have never been in the same room. Minutes also need no model -- the
    motion and roll-call form is a pattern -- so this is the part of the frontier
    a contributor can finish on a laptop.
    """
    from groundtruth.frontier import build

    f = build([{"place": "Brantford", "period": "1962"}])
    decisions = [q for q in f.questions if q.kind == "decision"]
    assert len(decisions) == 1
    q = decisions[0]
    assert "Brantford" in q.text
    assert q.have == ["Brantford"]
    assert not q.answerable            # the minutes have not been read
    assert q.distance == 1


def test_a_decision_question_ranks_a_town_whose_numbers_are_already_read():
    from groundtruth.frontier import build

    f = build([{"place": "Brantford", "period": "1962"}])
    ranked = {r["place"]: r for r in f.ranked_places()}
    assert "Brantford council minutes" in ranked
