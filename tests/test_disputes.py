"""Tests for open contribution with nobody adjudicating.

The property under test is not "good claims win". It is that no path exists by
which a claim with no evidence changes what is shown -- because the moment one
does, somebody has to decide, and deciding is the thing this design refuses to
build.
"""

from __future__ import annotations

import pytest

from concordance.disputes import (
    Claim, Flag, Ledger, Slot, check, resolve, slot_of,
)

PAGE = (
    "The average influent BOD and suspended solids were 104 mg/1 and 224 mg/1 "
    "respectively. The average effluent BOD and suspended solids were 37 mg/1 "
    "and 36 mg/1 respectively, giving an average removal of 64% BOD."
)
#: The same figures reprinted in the summary at the back, which is how a real
#: report disagrees with itself: on two pages, not on one.
LATER_PAGE = (
    "In summary, influent BOD averaged 26 mg/1 over the year and the works "
    "performed to specification throughout."
)
PAGES = {"owensound": {7: PAGE, 30: LATER_PAGE}}


def _claim(value, quote, *, source="extraction", parameter="BOD",
           stream="influent", contributor="anonymous", note="", page=7):
    return Claim(
        record={
            "kind": "observation", "parameter": parameter, "value": value, "unit": "mg/L",
            "place": "Owen Sound", "facility": "sewage", "period": "1969",
            "stream": stream,
            "provenance": {"identifier": "owensound", "page": page,
                           "source_text": quote},
        },
        source=source, contributor=contributor, note=note,
    )


def _check(claim):
    return check(claim, pages={k: dict(v) for k, v in PAGES.items()})


# -- the archive decides ----------------------------------------------------

def test_a_real_sentence_with_its_real_number_verifies():
    s = _check(_claim(104, "The average influent BOD and suspended solids were 104 mg/1"))
    assert s.verified


def test_an_invented_sentence_fails():
    s = _check(_claim(104, "The plant was overwhelmed by a flood in March."))
    assert not s.verified
    assert "not on that page" in s.why


def test_changing_the_number_while_keeping_the_real_sentence_fails():
    """The obvious way to poison a contribution, and the one a sentence check
    alone cannot see."""
    s = _check(_claim(999, "The average influent BOD and suspended solids were 104 mg/1"))
    assert not s.verified


def test_a_claim_with_no_page_or_quote_cannot_verify():
    c = Claim(record={"parameter": "BOD", "value": 104, "provenance": {}})
    assert not _check(c).verified


def test_who_submitted_it_makes_no_difference():
    quote = "The average influent BOD and suspended solids were 104 mg/1"
    mine = _check(_claim(104, quote, source="extraction", contributor="gemma4:12b"))
    theirs = _check(_claim(104, quote, source="person", contributor="a stranger"))
    assert mine.verified == theirs.verified is True

    bad_mine = _check(_claim(999, quote, source="extraction"))
    bad_theirs = _check(_claim(999, quote, source="person"))
    assert bad_mine.verified == bad_theirs.verified is False


# -- corrections win without anyone deciding --------------------------------

def test_an_evidenced_correction_replaces_an_unevidenced_record():
    wrong = _claim(999, "The plant processed 999 mg/1 of BOD.")          # not on page
    right = _claim(104, "The average influent BOD and suspended solids were 104 mg/1",
                   source="correction")
    ledger = resolve([wrong, right], archive=_FakeArchive())
    slot = next(iter(ledger.slots.values()))
    assert slot.state == "settled"
    assert slot.values == [104]
    assert len(slot.rejected) == 1


# -- nobody wins when both are real -----------------------------------------

def test_two_readings_of_one_sentence_are_shown_not_chosen_between():
    """The failure verification cannot catch, in its real form.

    "The average influent BOD and suspended solids were 104 mg/1 and 224 mg/1
    respectively" pairs two parameters with two values by word order alone. Read
    it the wrong way round and influent BOD becomes 224 -- the same slot, the
    same real sentence, and a number that is genuinely in it. Every check
    passes. The machine has no basis to prefer either; a reader looking at the
    crop has an excellent one.
    """
    quote = ("The average influent BOD and suspended solids were 104 mg/1 and "
             "224 mg/1 respectively")
    a = _claim(104, quote, stream="influent")
    b = _claim(224, quote, stream="influent")
    ledger = resolve([a, b], archive=_FakeArchive())
    slot = next(iter(ledger.slots.values()))
    assert slot.state == "contested"
    assert sorted(slot.values) == [104, 224]
    assert slot.same_sentence
    assert len(slot.surviving) == 2


def test_a_contested_slot_names_the_disagreement_as_one_sentence_or_two():
    """A report contradicting itself does it across pages -- the body says one
    thing and the summary at the back says another."""
    a = _claim(104, "The average influent BOD and suspended solids were 104 mg/1")
    b = _claim(26, "In summary, influent BOD averaged 26 mg/1 over the year", page=30)
    slot = next(iter(resolve([a, b], archive=_FakeArchive()).slots.values()))
    assert slot.state == "contested"
    assert not slot.same_sentence          # two sentences, not one ambiguity


def test_two_sentences_on_one_page_are_a_listing_rather_than_a_contradiction():
    """This test used to assert "contested", and it was wrong in the same way
    the portal was.

    Influent 104 and effluent 37 are not two answers to one question. They are
    two rows of one table, and the word that separates them -- influent,
    effluent -- is right there in the quote while the slot key drops it. Real
    examples from the corpus: "HP - 60" against "HP - 30" for two pumps in one
    station, and 300 feet of 33-inch pipe against 1179 feet of 36-inch.

    Calling those contradictions asks a reader to adjudicate between two pipes.
    """
    a = _claim(104, "The average influent BOD and suspended solids were 104 mg/1")
    b = _claim(37, "The average effluent BOD and suspended solids were 37 mg/1")
    slot = next(iter(resolve([a, b], archive=_FakeArchive()).slots.values()))
    assert slot.state == "undistinguished"
    assert slot.undistinguished
    assert not slot.same_sentence
    # And it must not be smuggled back into the disagreements.
    assert slot not in resolve([a, b], archive=_FakeArchive()).contested()


def test_one_ambiguous_sentence_read_two_ways_is_still_a_real_disagreement():
    """The guard on the rule above: identical quotes are not a listing."""
    quote = ("The average influent BOD and suspended solids were 104 mg/1 and "
             "224 mg/1 respectively")
    slot = next(iter(resolve([_claim(104, quote), _claim(224, quote)],
                             archive=_FakeArchive()).slots.values()))
    assert slot.state == "contested"
    assert slot.same_sentence


# -- flags never change anything --------------------------------------------

def test_a_flag_cannot_unseat_an_evidenced_record():
    """The whole design rests on this. If an unevidenced objection could hide a
    record, somebody would have to judge the objection."""
    good = _claim(104, "The average influent BOD and suspended solids were 104 mg/1")
    ledger = resolve([good], [Flag(claim_id=good.id, reason="looks too high")] * 40,
                     archive=_FakeArchive())
    slot = next(iter(ledger.slots.values()))
    assert slot.state == "settled"
    assert slot.values == [104]
    assert len(slot.flags) == 40           # counted, shown, and inert


def test_flags_are_visible_where_people_raised_them():
    good = _claim(104, "The average influent BOD and suspended solids were 104 mg/1")
    ledger = resolve([good], [Flag(claim_id=good.id, reason="wrong stream")],
                     archive=_FakeArchive())
    top = ledger.most_flagged()
    assert top and top[0]["flags"] == 1
    assert "wrong stream" in top[0]["reasons"][0]


def test_a_flag_for_an_unknown_claim_is_dropped_rather_than_guessed_at():
    good = _claim(104, "The average influent BOD and suspended solids were 104 mg/1")
    ledger = resolve([good], [Flag(claim_id="nosuchclaim")], archive=_FakeArchive())
    assert sum(len(s.flags) for s in ledger.slots.values()) == 0


# -- slots ------------------------------------------------------------------

def test_two_facilities_in_one_town_are_different_measurements():
    """Merging Owen Sound's sewage plant with its water works once made the
    town's record appear to run twenty years longer than it does."""
    sewage = {"place": "Owen Sound", "facility": "sewage",
              "parameter": "BOD", "unit": "mg/L", "period": "1969"}
    water = dict(sewage, facility="water supply")
    assert slot_of(sewage) != slot_of(water)


def test_the_report_admits_what_verification_cannot_do():
    ledger = resolve([_claim(104, "The average influent BOD and suspended solids "
                                  "were 104 mg/1")], archive=_FakeArchive())
    report = ledger.report()
    assert any("RIGHT reading" in n for n in report["not_measured"])
    assert any("good faith" in n for n in report["not_measured"])


class _FakeArchive:
    """Stands in for the network. `resolve` fetches each item once."""

    def pages(self, identifier):
        class P:
            def __init__(self, page, text):
                self.page, self.text = page, text
        return [P(p, t) for p, t in PAGES.get(identifier, {}).items()]


# -- the scanner's crime, not the extractor's -------------------------------

def test_a_value_written_with_scanner_letters_still_verifies():
    """1960s scans render 15 as "I5" and 31 as "3I". The strict digit check
    convicted the extractor of the scanner's crime and threw away correct
    readings -- three of the 29 unsupported slots in the first real run."""
    page = {"doc": {1: 'Each pass of the aeration tanks is 30 feet wide, I5 feet deep.'}}
    c = Claim(record={
        "kind": "observation", "parameter": "depth", "value": 15, "unit": "feet",
        "provenance": {"identifier": "doc", "page": 1,
                       "source_text": "is 30 feet wide, I5 feet deep"}})
    s = check(c, pages={k: dict(v) for k, v in page.items()})
    assert s.verified
    assert "OCR letter-for-digit damage" in s.why


def test_relaxing_the_digits_does_not_relax_the_sentence():
    """The only thing loosened is how the sentence's own characters are read.
    An invented sentence still fails, so nothing can be smuggled in."""
    page = {"doc": {1: "The plant ran well."}}
    c = Claim(record={
        "kind": "observation", "parameter": "depth", "value": 15, "unit": "feet",
        "provenance": {"identifier": "doc", "page": 1,
                       "source_text": "I5 feet deep"}})
    assert not check(c, pages={k: dict(v) for k, v in page.items()}).verified


def test_a_genuinely_wrong_number_is_still_rejected():
    page = {"doc": {1: "A total of 16,120,000 gallons of raw sludge was pumped."}}
    c = Claim(record={
        "kind": "observation", "parameter": "raw sludge volume", "value": 16200000,
        "unit": "gallons",
        "provenance": {"identifier": "doc", "page": 1,
                       "source_text": "A total of 16,120,000 gallons of raw sludge was pumped"}})
    assert not check(c, pages={k: dict(v) for k, v in page.items()}).verified


# -- influent is not effluent -----------------------------------------------

def test_influent_and_effluent_are_not_the_same_measurement():
    """Brantford's 1962 raw sewage was 210 ppm BOD and its final effluent 10
    ppm. Filed in one slot the ledger reports a contradiction, when what it is
    actually looking at is the plant working."""
    raw = dict(place="Brantford", facility="wpcp", parameter="BOD",
               unit="ppm", period="1962", stream="raw")
    final = dict(raw, stream="effluent")
    assert slot_of(raw) != slot_of(final)


# -- submitting one, as a person --------------------------------------------

def test_a_person_s_reading_is_accepted_by_the_page_not_by_anyone(tmp_path):
    """No queue, no account, no reputation -- none of which the check consults."""
    from concordance.disputes import submit

    good = submit(
        {"kind": "observation", "parameter": "BOD", "value": 104, "unit": "mg/L", "place": "Owen Sound",
         "facility": "sewage", "period": "1969", "stream": "influent",
         "provenance": {"identifier": "owensound", "page": 7,
                        "source_text": "The average influent BOD and suspended "
                                       "solids were 104 mg/1"}},
        contributor="a stranger", archive=_FakeArchive(), directory=tmp_path)
    assert good.standing.verified and good.stored
    assert "on the same footing" in good.to_dict()["what_happens_now"]


def test_a_refused_submission_deletes_nothing_and_blames_nobody(tmp_path):
    from concordance.disputes import submit

    bad = submit(
        {"kind": "observation", "parameter": "BOD", "value": 104, "unit": "mg/L", "place": "Owen Sound",
         "provenance": {"identifier": "owensound", "page": 7,
                        "source_text": "A flood destroyed the plant in March."}},
        contributor="a stranger", archive=_FakeArchive(), directory=tmp_path)
    assert not bad.standing.verified and not bad.stored
    assert list(tmp_path.glob("*.json")) == []
    assert "the page did" in bad.to_dict()["what_happens_now"]


def test_a_contribution_reads_back_indistinguishable_from_the_machine_s(tmp_path):
    """Nothing on disk records who to believe, because nothing ever asks."""
    from concordance.disputes import check, load_contributions, submit

    record = {"kind": "observation", "parameter": "BOD", "value": 104, "unit": "mg/L",
              "place": "Owen Sound", "facility": "sewage", "period": "1969",
              "stream": "influent",
              "provenance": {"identifier": "owensound", "page": 7,
                             "source_text": "The average influent BOD and "
                                            "suspended solids were 104 mg/1"}}
    submit(record, contributor="a stranger", archive=_FakeArchive(), directory=tmp_path)

    theirs = load_contributions(tmp_path)
    assert len(theirs) == 1
    mine = Claim(record=record, source="extraction", contributor="gemma4:12b")
    assert theirs[0].slot == mine.slot
    assert _check(theirs[0]).verified == _check(mine).verified is True


# -- a table reading has headings, not a sentence ---------------------------

TABLE_OCR = (
    "TABLE I FLOW - MILX.IQN GALLOLS MONTH MAX. DAILY r low MIN. DAILY "
    "Jan. 6.976 4.609 5.700 176.547 Feb. 6.200 4.377 5.425 151.607"
)
TABLE_PAGES = {"brantford": {15: TABLE_OCR}}


def _cell_claim(value, cell="table cell [Jan. / MAX. DAILY Flow]"):
    return Claim(record={
        "kind": "observation", "parameter": "MAX. DAILY Flow", "value": value, "unit": "million gallons",
        "place": "Brantford", "period": "1962",
        "provenance": {"identifier": "brantford", "page": 15, "source_text": cell},
    })


def _check_table(claim):
    return check(claim, pages={k: dict(v) for k, v in TABLE_PAGES.items()})


def test_a_table_heading_pair_without_localized_cell_proof_abstains():
    """Headings plus a page-wide number do not prove their intersection."""
    standing = _check_table(_cell_claim(6.976))
    assert not standing.verified
    assert "localized cell evidence" in standing.why


def test_a_table_value_that_is_not_in_the_page_digits_is_refused():
    s = _check_table(_cell_claim(9999.1))
    assert not s.verified
    assert "localized cell evidence" in s.why


def test_a_cited_heading_that_is_not_on_the_page_is_refused():
    s = _check_table(_cell_claim(6.976, "table cell [Jan. / RAINFALL]"))
    assert not s.verified
    assert "headings cited are not on that page" in s.why


def test_a_page_whose_ocr_cannot_referee_headings_does_not_verify():
    """Damaged OCR is a reason to abstain, never positive evidence for import."""
    pages = {"x": {1: "STATEMENT No. 4 Continued. SUMMIT WATER SUPPLY. 41.2"}}
    c = Claim(record={
        "kind": "observation", "parameter": "discharge", "value": 41.2, "unit": "cu ft",
        "provenance": {"identifier": "x", "page": 1,
                       "source_text": "table cell [Talon Lake / Evaporation]"}})
    s = check(c, pages={k: dict(v) for k, v in pages.items()})
    assert not s.verified
    assert "cannot referee" in s.why


def test_prose_records_are_unaffected():
    """The dispatch must not weaken the sentence check it sits beside."""
    assert not _check(_claim(999, "The average influent BOD and suspended "
                                  "solids were 104 mg/1")).verified
