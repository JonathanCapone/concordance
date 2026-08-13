"""Tests for the decision record.

Weighted toward the failures that produce a *readable* wrong answer: a person
who never existed, a vote list that swallowed the next paragraph, a councillor
recorded as opposing something they voted for. A crash in this module would be
noticed in a minute. A misattributed vote would be quoted.
"""

from __future__ import annotations

from concordance.decisions import (
    Ledger, Motion, Roll, clean_name, read_document, read_page,
)
from concordance.models import PageText


def _page(text: str, page: int = 1) -> PageText:
    return PageText(identifier="hamilton1992", page=page, text=text)


# -- motions ----------------------------------------------------------------

def test_reads_mover_seconder_and_outcome():
    m = read_page(_page(
        "It was moved by Alderman Eisenberger and seconded by Alderman Morelli "
        "that the Building Commissioner be authorized to issue a demolition "
        "permit for 336-338 Jackson Street West. CARRIED."
    ))
    assert len(m) == 1
    assert m[0].moved_by == "Eisenberger"
    assert m[0].seconded_by == "Morelli"
    assert m[0].outcome == "carried"
    assert "demolition" in m[0].text


def test_a_name_does_not_swallow_the_following_word():
    """The bug that made "Kiss that" the second most active councillor.

    These patterns need re.I to catch "IT WAS MOVED BY", but under that flag
    [A-Z] also matches lowercase, so the seconder ran on into the word "that".
    The false person then accumulated 26 seconds and appeared in the ledger
    above every real alderman.
    """
    m = read_page(_page(
        "It was moved by Alderman Cooke and seconded by Alderman Kiss that the "
        "Report of the Committee of the Whole be adopted. CARRIED."
    ))
    assert m[0].seconded_by == "Kiss"
    assert "that" not in m[0].seconded_by.lower()


def test_outcome_of_the_next_motion_is_not_borrowed():
    text = (
        "It was moved by Alderman Cooke and seconded by Alderman Kiss that the "
        "first matter be approved. "
        "It was moved by Alderman Copps and seconded by Alderman Ross that the "
        "second matter be approved. DEFEATED."
    )
    first, second = read_page(_page(text))[:2]
    assert second.outcome == "defeated"
    assert first.outcome != "defeated"


def test_a_motion_needs_two_real_names():
    """Prose containing the words must not become a motion."""
    assert read_page(_page(
        "The report notes that the motion was moved by the committee and "
        "seconded by the board without discussion."
    )) == []


# -- rolls ------------------------------------------------------------------

ROLL = (
    "Recorded vote. YEAS: Mayor Morrow, Aldermen Cooke, Kiss, Agro, McCulloch, "
    "Morelli, Copps, Wilson, Agostino, Eisenberger, Charters, Jackson, Merling, "
    "Anderson, D'Amico, Ross. -16. NAYS: -0. CARRIED."
)


def test_recorded_vote_parses_every_name_and_reconciles():
    m = read_page(_page("Re: Promotional Banner Across Main Street West " + ROLL))
    assert len(m) == 1
    yea = next(r for r in m[0].rolls if r.cast == "yea")
    assert len(yea.people) == 16
    assert yea.stated_count == 16
    assert yea.agrees
    assert "Morrow" in yea.people and "D'Amico" in yea.people


def test_empty_nays_stays_empty_despite_scanner_dirt():
    """The bug the clerk's own tally caught.

    "NAYS: �-0." -- a speck of dirt before the count -- stopped the count
    from matching, so the empty list ran on and absorbed the following
    paragraph. Twelve councillors who voted in favour were recorded as voting
    against. 17 of 47 divisions were wrong this way.
    """
    text = (
        "Re: Market Value Assessment Recorded vote. "
        "YEAS: Mayor Morrow, Aldermen Cooke, Kiss. -3. NAYS: �-0. * CARRIED. "
        "It was moved by Alderman Cooke and seconded by Alderman Kiss that the "
        "Report of the Committee of the Whole be adopted."
    )
    division = read_page(_page(text))[0]
    nays = next(r for r in division.rolls if r.cast == "nay")
    assert nays.people == []
    assert nays.stated_count == 0
    assert division.unanimous is True


def test_a_roll_that_does_not_add_up_is_reported_not_hidden():
    r = Roll(cast="yea", people=["Cooke", "Kiss"], stated_count=16)
    assert not r.agrees
    m = Motion(text="x", moved_by="a", seconded_by="b", rolls=[r])
    assert not m.rolls_agree


def test_division_without_a_mover_is_still_a_decision():
    """Most recorded votes here hang off a committee section, not a motion.

    Requiring a mover discarded all 40 divisions in the first volume tested.
    """
    m = read_page(_page("Re: Red Hill Creek Expressway property acquisitions " + ROLL))
    assert m[0].moved_by == ""
    assert m[0].recorded
    assert "Red Hill Creek" in m[0].text
    assert Ledger.motions_of(m) == m


def test_yeas_and_nays_are_one_division_not_two():
    m = read_page(_page("Re: something " + ROLL))
    assert len(m) == 1
    assert {r.cast for r in m[0].rolls} == {"yea", "nay"}


# -- people -----------------------------------------------------------------

def test_ledger_counts_moves_seconds_and_votes():
    led = read_document([
        _page("It was moved by Alderman Cooke and seconded by Alderman Kiss "
              "that the grant be approved. CARRIED.", page=1),
        _page("Re: Capital Grant to McMaster University " + ROLL, page=2),
    ], body="City Council of Hamilton", year="1992")

    cooke = led.people["cooke"]
    assert cooke.moved == 1
    assert cooke.votes["yea"] == 1
    assert "City Council of Hamilton" in cooke.bodies
    assert led.people["kiss"].seconded == 1


def test_dissent_is_findable():
    led = Ledger()
    led.add(read_page(_page(
        "Re: Red Hill Creek Expressway property acquisitions Recorded vote. "
        "YEAS: Mayor Morrow, Aldermen Cooke, Kiss. -3. NAYS: Alderman Copps. -1. CARRIED."
    )))
    assert led.dissenters()[0]["person"] == "Copps"
    divided = led.divided_motions()
    assert divided and divided[0]["against"] == ["Copps"]
    assert "Red Hill Creek" in divided[0]["text"]


def test_apostrophes_fold_but_spellings_are_not_guessed():
    assert clean_name("D�Amico") == "D'Amico"
    assert clean_name("D’Amico") == "D'Amico"
    # An OCR-damaged surname stays as it is: deciding two spellings are one
    # person is a judgement, and judgements about identity belong with a person.
    assert clean_name("Eisenherger") == "Eisenherger"


def test_every_decision_carries_a_page_it_can_be_checked_against():
    for m in read_page(_page("Re: anything " + ROLL)):
        assert m.provenance is not None
        assert m.provenance.page_url.endswith("/mode/2up")
        assert "YEAS" in m.provenance.source_text


def test_a_carried_motion_is_not_recorded_as_an_outcome():
    """A resolution is a promise. The report must say so in its own output."""
    led = Ledger()
    led.add(read_page(_page(
        "It was moved by Alderman Cooke and seconded by Alderman Kiss that the "
        "expressway be built. CARRIED."
    )))
    assert any("carried out" in n for n in led.report()["not_measured"])
