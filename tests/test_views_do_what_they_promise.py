"""Each view must answer the question its label asks, and cite what it claims.

An audit exercised all eight views against a live instance. Seven of eight
showed something other than what their new label promised, and the same defect
appeared in four of them: a number on screen that resolves to nothing.

That is the one claim this whole project rests on.
"""

from __future__ import annotations

import pytest

import concordance.server as S


@pytest.fixture(scope="module")
def state() -> S.State:
    return S.State()


# -- What stopped -----------------------------------------------------------

def test_the_silence_view_names_its_places(state: S.State) -> None:
    """It reported that 72 of 107 series stopped and never said which.
    /api/quiet has always carried the places; the loader never read them."""
    # The endpoint calls what_went_quiet(); State.silence is only the stored
    # report file and does not carry the places.
    from concordance.tools import what_went_quiet

    quiet = what_went_quiet()
    if not quiet.get("available", True):
        pytest.skip("no silence report")
    places = quiet.get("places") or []
    assert places, "the report carries no places"
    for p in places[:5]:
        assert p.get("place") and p.get("last_year")
    page = state.html()
    assert "d.places" in page or "quiet-list" in page, "the view still discards them"


def test_stopped_is_distinguishable_from_never_read(state: S.State) -> None:
    """89 of the 107 have never been read. "We did not read it" and "the record
    stops" are different facts and must not look alike."""
    page = state.html()
    assert "quiet unread" in page and "quiet read" in page
    assert "not read" in page


# -- Can I trust it ---------------------------------------------------------

def test_every_accuracy_figure_carries_its_sample(state: S.State) -> None:
    """96.8% on four hand-read pages reads, undenominated, as a guarantee.
    The API always sent matched/missed/spurious and stream_pairs_judged."""
    page = state.html()
    assert "measured on" in page, "the accuracy table has no sample column"
    assert "stream_pairs_judged" in page
    assert "matched" in page


def test_a_missing_gold_report_is_not_zero_accuracy(state: S.State) -> None:
    """Printing 0.0% because no run is published would be the worst possible
    lie in the one view whose job is honesty."""
    page = state.html()
    assert "No scored run is published yet" in page


def test_stream_accuracy_says_not_judged_rather_than_zero(state: S.State) -> None:
    page = state.html()
    assert "not judged" in page


# -- Disagreements ----------------------------------------------------------

def test_the_ledger_says_how_much_of_itself_it_is_showing(state: S.State) -> None:
    """It rendered 40 of 267, all from one town, under a heading saying 267."""
    led = state.ledger()
    assert led.get("contested_total") is not None
    assert led.get("contested_shown") is not None
    assert led["contested_shown"] <= led["contested_total"]
    assert "of" in state.html()


def test_the_contested_sample_spans_places(state: S.State) -> None:
    """The first forty in load order were all Belleville, because
    belleville.json loads first."""
    led = state.ledger()
    detail = led.get("contested_detail") or []
    if len(detail) < 5:
        pytest.skip("too few contested slots to spread")
    places = {str(x["slot"]).split("|")[0] for x in detail}
    assert len(places) > 1, f"every shown disagreement is from {places}"


# -- Who decided ------------------------------------------------------------

def test_a_roll_with_no_tally_is_not_reported_as_reconciled() -> None:
    """`agrees` returns True when the clerk wrote no tally -- nothing has been
    contradicted, which is not the same as having been checked. Four fifths of
    rolls carry no tally, so reporting those as agreeing is a control that
    passes when there is nothing to check."""
    from concordance.decisions import Roll

    no_tally = Roll(cast="yea", people=["Cooke", "Kiss"], stated_count=None)
    assert no_tally.agrees is True
    assert no_tally.checked is False

    checked = Roll(cast="yea", people=["Cooke", "Kiss"], stated_count=2)
    assert checked.checked is True and checked.agrees is True

    wrong = Roll(cast="yea", people=["Cooke", "Kiss"], stated_count=9)
    assert wrong.checked is True and wrong.agrees is False


def test_a_motion_resolves_to_its_page() -> None:
    """"81 carried" resolved to nothing: no text, no quote, no scan.
    Motion.to_dict already carried all of it and nothing called it."""
    from concordance.decisions import Ledger

    report = Ledger().report()
    assert "motions_detail" in report
    assert "rolls_checkable" in report and "rolls_with_no_tally" in report
    assert "motions_detail" in S.State().html() or "The motions" in S.State().html()


# -- a table listing is not a disagreement ----------------------------------

def test_one_page_listing_several_values_is_not_a_disagreement() -> None:
    """A pumping station's spec table gave "HP - 60" and "HP - 30" for one
    slot, and the ledger called it a contradiction. They are two pumps.

    In every instance in this corpus the distinguishing detail is sitting in
    the quote while the slot key throws it away -- two pipes of 33 and 36
    inches, two contracts numbered 58-S-17 and 61-S-77, three tanks of
    different volumes. Inviting a reader to adjudicate between a 33-inch pipe
    and a 36-inch one is worse than useless.
    """
    from concordance.disputes import Claim, Slot, Standing

    def _standing(value, quote, page):
        return Standing(Claim(record={
            "parameter": "horsepower", "value": value, "unit": "hp",
            "provenance": {"identifier": "vol", "page": page,
                           "source_text": quote}}), True, "on the page")

    same_page = Slot(key="belleville|pumping station|horsepower|hp|1964")
    same_page.standings = [_standing(60.0, "HP - 60", 12),
                           _standing(30.0, "HP - 30", 12)]
    assert same_page.undistinguished is True
    assert same_page.state == "undistinguished"

    # Two pages disagreeing IS a disagreement and must stay one.
    two_pages = Slot(key="owen sound|plant|bod|mg/l|1969")
    two_pages.standings = [_standing(104.0, "The average influent BOD was 104 mg/1.", 9),
                           _standing(26.0, "Influent BOD averaged 26 mg/1.", 30)]
    assert two_pages.undistinguished is False
    assert two_pages.state == "contested"


def test_the_ledger_counts_listings_apart_from_disagreements(state: S.State) -> None:
    led = state.ledger()
    assert "undistinguished" in led
    assert led["undistinguished"] >= 0
    assert "listed together" in state.html()


def test_a_listing_links_the_page_the_way_the_archive_numbers_it(state: S.State) -> None:
    """archive.org's leaf index is zero-based and ours is not. Built in the
    browser this was off by one and pointed at the facing page.
    """
    from concordance.models import Provenance

    for slot in state.ledger()["listed_detail"]:
        assert slot["page_url"] == Provenance(
            identifier=slot["identifier"], page=slot["page"]).page_url
        assert slot["page_url"].startswith("https://archive.org/details/")
