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


# -- a sub-unit is not a facility -------------------------------------------

def test_a_bare_unit_number_is_reattached_to_the_plant_in_its_own_document() -> None:
    """"Unit No. 1" is a pump inside a plant. Recorded as the facility, its
    readings appeared on no page at all -- nobody browses to a plant called
    Unit No. 1 -- and where two sub-units shared a name their readings collided
    and the ledger called two pumps a contradiction.
    """
    from concordance.places import attach_subunits

    def _rec(facility, value, ident="doc"):
        return {"parameter": "horsepower", "value": value, "unit": "HP",
                "facility": facility, "kind": "design",
                "provenance": {"identifier": ident, "page": 24}}

    out = attach_subunits([
        _rec("water pollution control plant", 7.5),
        _rec("water pollution control plant", 25.0),
        _rec("Unit No. 1", 50.0),
        _rec("Unit No. 2", 40.0),
    ])
    assert out[2]["raw"]["parent_facility"] == "water pollution control plant"
    assert out[3]["raw"]["parent_facility"] == "water pollution control plant"
    # The record's own identity is untouched. Rewriting facility here made the
    # library's published data re-import as 88 new records, because the same
    # reading carried a different name on either side of the loader.
    assert out[2]["facility"] == "Unit No. 1"
    assert out[3]["facility"] == "Unit No. 2"


def test_an_orphan_stays_an_orphan_when_its_document_names_no_plant() -> None:
    """Adoption by whatever was nearest would be an invention."""
    from concordance.places import attach_subunits

    only = [{"parameter": "horsepower", "value": 50.0, "facility": "Unit No. 1",
             "provenance": {"identifier": "doc", "page": 3}}]
    assert attach_subunits(only)[0]["facility"] == "Unit No. 1"

    # Nor from a different document.
    two = only + [{"parameter": "flow", "value": 1.0, "facility": "sewage plant",
                   "provenance": {"identifier": "other-doc", "page": 3}}]
    assert attach_subunits(two)[0]["facility"] == "Unit No. 1"


def test_the_place_page_counts_what_the_place_page_shows(state: S.State) -> None:
    """It read "97 observations from 2 documents" above 448 rows drawn from
    twelve. The helper it took those from reports one facility on purpose; this
    page shows them all.
    """
    town = state.town("belleville", "Belleville")
    rows = [r for panel in town["series"] + town["singles"]
            for r in (panel.get("rows") or [])]
    observations = [r for r in rows if r.get("kind") == "observation"]
    assert town["n_measurements"] == len(observations)
    assert set(town["sources"]) == {r["identifier"] for r in rows if r["identifier"]}


def test_a_figure_is_shown_under_the_thing_the_document_describes(state: S.State) -> None:
    """The general defect, of which the pumps were one instance.

    A spec page describes a machine; a water-quality table describes a sampling
    site; a tender schedule describes a contract. Filed by parameter, every one
    of them becomes a number with its subject removed -- "horsepower: 60" and
    "horsepower: 30" under a heading that cannot say what either belongs to.
    """
    town = state.town("belleville", "Belleville")
    design = next(s for s in town["other"] if s["kind"] == "design")

    plant = next(s for s in design["subjects"]
                 if s["name"] == "water pollution control plant")
    unit = next(u for u in plant["units"] if u["name"] == "Unit No. 1")
    specs = {s["parameter"]: f'{s["value"]} {s["unit"]}' for s in unit["specs"]}
    # The pump, described -- not four unrelated parameter categories.
    assert specs["motor horsepower"] == "50 HP"
    assert specs["motor RPM"] == "1,200 RPM"
    assert "design capacity" in specs

    sibling = next(u for u in plant["units"] if u["name"] == "Unit No. 2")
    assert sibling["specs"] != unit["specs"]


def test_a_figure_with_no_subject_is_said_to_have_none(state: S.State) -> None:
    """Grouped under a name that admits it, and counted, rather than filed
    under a parameter as though the parameter were the subject."""
    town = state.town("belleville", "Belleville")
    assert town["without_subject"] + town["with_subject"] > 0
    for section in town["other"]:
        for subject in section["subjects"]:
            assert subject["name"]
            if subject["name"] == S.UNATTRIBUTED:
                assert subject["units"]


def test_a_measurement_is_readable_without_an_exponent(state: S.State) -> None:
    """26,200 imperial gallons was rendering as 2.62e+04 on a page whose whole
    argument is that a resident can read it."""
    assert S._number(26200) == "26,200"
    assert S._number(0.5) == "0.5"
    assert S._number(1179) == "1,179"
    # An annual sludge volume of 14,760,000 gallons is an ordinary figure here.
    assert S._number(14760000) == "14,760,000"
    # Genuinely huge and genuinely tiny keep the exponent.
    assert "e" in S._number(8e9)
    assert "e" in S._number(0.0000012)

    town = state.town("belleville", "Belleville")
    rows = [r for panel in town["series"] + town["singles"]
            for r in (panel.get("rows") or [])]
    assert rows
    assert not [r for r in rows if "e+" in str(r["value"])]


def test_a_spec_restated_by_the_next_report_is_one_spec(state: S.State) -> None:
    """Belleville's grit tank held 26,200 gallons in the 1964 report and in the
    1965 one. The panel listed it twice, as though the tank kept being rebuilt
    to the same size.

    Collapsed to one line -- but every restatement keeps its own page, because
    "the 1970 report still says 26,200" is a checkable claim, and a spec that
    quietly CHANGES between reports must stay two lines.
    """
    town = state.town("belleville", "Belleville")
    design = next(s for s in town["other"] if s["kind"] == "design")
    tank = next(s for s in design["subjects"] if s["name"] == "Aerated grit tank")
    specs = [s for u in tank["units"] for s in u["specs"]]

    volume = next(s for s in specs if s["parameter"] == "Liquid Volume")
    assert volume["period"] == "1964"
    assert [r["period"] for r in volume["restatements"]] == ["1965"]
    assert all(r["page"] and r["page_url"] for r in volume["restatements"])

    # One line per distinct figure, not one per report that mentioned it.
    assert len([s for s in specs if s["parameter"] == "Liquid Volume"]) == 1


def test_a_changed_spec_is_not_collapsed() -> None:
    """The interesting case: a plant rebuilt between reports."""
    groups = {("", "pump house"): [
        {"parameter": "capacity", "value": "2", "unit": "MGD", "period": "1964",
         "page": 3, "page_url": "u", "identifier": "i", "quote": "q"},
        {"parameter": "capacity", "value": "5", "unit": "MGD", "period": "1971",
         "page": 8, "page_url": "u", "identifier": "i", "quote": "q"},
    ]}
    specs = S._subjects(groups)[0]["units"][0]["specs"]
    assert [s["value"] for s in specs] == ["2", "5"]
    assert all(not s["restatements"] for s in specs)
