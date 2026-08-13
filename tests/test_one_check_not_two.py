"""The ledger and the bundle must reach the same verdict about the same record.

They did not. `disputes.check` undid the scanner's letter-for-digit damage
before judging a value; `contribute.verify_bundle` did not. So a reading this
instance had verified and published was REFUSED when the identical reading
arrived from somebody else in a bundle -- eight of eleven refusals on a real
push of the Brantford record, every one of them a correct reading of a page.

A distributed system whose two verification paths disagree does not have a
verification rule; it has two, and the contributor discovers which one they got
by whether their work was thrown away.
"""

from __future__ import annotations

from concordance.contribute import _value_in_quote
from concordance.disputes import Claim, check

# Real sentences from the archive, with what a correct reader returns.
SCANNED = [
    (15.0, "is 30 feet wide, I5 feet deep and 200 feet long."),
    (190.0, "from I96I when, the average BOD and SS were I90 and 220 respectively."),
    (31.0, "was only 3I per cent of the sludge pumped to the digesters."),
    (13.0, "the concentrations in the final effluent are 10 and I3 ppm."),
    (0.05, "an aesthetic guideline of .05 mg/L,"),
    (0.5, "the Maximum Admissable Concentration is .50 mg/L and is set"),
    (0.21, "The Beryllium value of .21 ug/L in the November treated water sample"),
    (0.2, "Concentration of .20 ug/L for Beryllium in drinking water."),
    (8.8, "an average daily flow of 8. 8 million gallons"),
    (53549.66, "at an operating cost of 53,549.66 for the year"),
]

# Also real, and all three genuinely wrong. Kept because loosening the check is
# only safe if it still refuses these.
WRONG = [
    # A value guessed off OCR nobody could read.
    (366500.0, "the two units filtered a total of 3)Gl6,5^l'0 pounds of sludge"),
    # A transposition: the page says 16,120,000.
    (16200000.0, "A total of 16,120,000 gallons of raw sludge was pumped, "
                 "representing a decrease of 19% from 1968."),
    # DERIVED, not read: 6.57 / 52.5% = 12.5. The arithmetic is right and the
    # reading is still false, because the page never states this number.
    (12.6, "The average daily flow of 6. 57 million gallons is 8% higher than in "
           "1964 , however, it represents only 52. 5% of the plant design capacity."),
]


def _ledger(value: float, sentence: str) -> bool:
    claim = Claim(record={
        "parameter": "x", "value": value,
        "provenance": {"identifier": "doc", "page": 1, "source_text": sentence}})
    return check(claim, pages={"doc": {1: sentence}}).verified


def test_the_archive_is_read_as_it_was_scanned() -> None:
    for value, sentence in SCANNED:
        state, why = _value_in_quote(value, sentence)
        assert state == "ok", f"{value} refused from {sentence!r}: {why}"


def test_a_wrong_number_is_still_wrong() -> None:
    for value, sentence in WRONG:
        state, _ = _value_in_quote(value, sentence)
        assert state == "failed", f"{value} was accepted from {sentence!r}"


def test_both_paths_agree_on_every_case() -> None:
    """The property that actually matters, stated once."""
    for value, sentence in SCANNED + WRONG:
        bundle_ok = _value_in_quote(value, sentence)[0] == "ok"
        assert _ledger(value, sentence) == bundle_ok, (
            f"the ledger and the bundle disagree about {value} in {sentence!r}")


def test_verified_records_say_how_they_were_verified() -> None:
    """An allowance that is made silently is an allowance nobody can audit."""
    exact = _value_in_quote(104.0, "the average influent BOD was 104 mg/1")
    assert exact == ("ok", "")

    repaired = _value_in_quote(15.0, "I5 feet deep")
    assert repaired[0] == "ok" and "OCR" in repaired[1]

    as_number = _value_in_quote(0.05, "a guideline of .05 mg/L")
    assert as_number[0] == "ok" and as_number[1]


def test_an_invented_sentence_still_fails() -> None:
    """Nothing above loosens the sentence check, only how digits are read."""
    claim = Claim(record={
        "parameter": "BOD", "value": 104,
        "provenance": {"identifier": "doc", "page": 1,
                       "source_text": "The BOD was 104 mg/L."}})
    assert not check(claim, pages={"doc": {1: "A page about something else."}}).verified


# -- table readings ---------------------------------------------------------

def test_a_table_reading_verifies_in_a_bundle_as_it_does_in_the_ledger() -> None:
    """The third instance of two-checks-that-are-meant-to-be-one.

    A table reading cites row and column headings instead of a sentence, and
    verify_bundle had no path for that -- so "table cell [January - Janvier /
    Fine vacuum / 2002]" was judged as a sentence, was correctly found not to be
    one, and was recorded as fabrication. All 535 vision records failed, 100%,
    while the ledger verified those same records and published them.

    The work being refused was the contribution this project calls its most
    valuable: a person with a graphics card reading the tables nobody else can,
    once, for everyone.
    """
    from concordance.contribute import CELL_RE, make_bundle, verify_bundle
    from concordance.disputes import CELL_RE as LEDGER_CELL_RE, load_vision_records

    # One definition, not two that happen to agree today.
    assert CELL_RE is LEDGER_CELL_RE

    claims = load_vision_records()
    if not claims:
        import pytest
        pytest.skip("no vision records on disk")

    cells = [c for c in claims
             if CELL_RE.search((c.record.get("provenance") or {}).get("source_text") or "")]
    assert cells, "vision records should cite table cells"

    from concordance.archive import Archive
    verdict = verify_bundle(make_bundle([c.record for c in cells[:20]]),
                            archive=Archive())
    assert verdict.verified > 0, "table readings must not be refused as fabrication"
    assert not verdict.failed
