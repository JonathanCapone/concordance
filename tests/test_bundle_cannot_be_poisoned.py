"""What a hostile bundle can and cannot do to an instance.

/api/bundle is an unauthenticated write endpoint by design: the archive decides,
and asking who is speaking would contradict the whole claim. That only holds if
the archive is actually asked about every record, so these are the tests that
make the design safe rather than merely stated.

Every case here is one an audit found working against the shipped code.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from groundtruth.contribute import (
    _value_in_quote,
    make_bundle,
    merge_bundle,
    verify_bundle,
)


class FakeArchive:
    """Serves exactly one real page and refuses everything else."""

    PAGE = "The average influent BOD was 104 mg/1 in 1969, and the plant was " \
           "placed in service in 1913."

    def pages(self, identifier: str):
        if identifier != "item1":
            raise RuntimeError("item not found")

        class P:
            page, text = 11, FakeArchive.PAGE
        return [P()]


GENUINE = {
    "kind": "observation", "parameter": "BOD", "value": 104.0, "unit": "mg/L",
    "provenance": {"identifier": "item1", "page": 11,
                   "source_text": "The average influent BOD was 104 mg/1 in 1969"},
}


# -- the rounding hole ------------------------------------------------------

def test_a_round_number_cannot_ride_on_any_sentence_containing_its_first_digit():
    """The hole: values were accepted if their trailing zeros could be stripped
    down to a stub found anywhere in the sentence's digits. 3,000,000 reduces to
    "3", so it verified against any sentence containing a 3 -- and 62% of the
    quotes already in this repo accept the value 1,000,000 on that rule."""
    real_sentence = "The plant was placed in service in 1913 and served 3 villages."
    for fabricated in (3_000_000, 30_000, 1_000, 1_000_000, 2_000):
        state, why = _value_in_quote(fabricated, real_sentence)
        assert state == "failed", f"{fabricated} still rides on {real_sentence!r} ({why})"


def test_the_honest_readings_the_hole_was_covering_still_resolve_or_fail_visibly():
    """Removing it cost four records across the whole corpus, and two of those
    were the model guessing at destroyed OCR. Those now fail, which is where
    they belong -- not silently, but in the ledger with a reason."""
    state, _ = _value_in_quote(25_000, "two primary digesters with a total capacity "
                                       "of $0,000 cubic feet")
    assert state == "failed"


# -- one genuine record carrying fabrications -------------------------------

def _bundle_with(fabrications: list[dict]) -> dict:
    return make_bundle([GENUINE] + fabrications, contributor="someone")


def test_records_that_cite_nothing_are_not_merged():
    """They used to be. `unchecked` meant both "the sentence is on the page but
    the value is unjudgeable" and "nothing was checked at all", and everything
    not outright FAILED was merged -- so one real record carried any number of
    inventions into the library, and the response said nothing was taken on
    trust."""
    fabrications = [{"kind": "observation", "parameter": "mercury", "value": 9.9,
                     "provenance": {}} for _ in range(50)]
    bundle = _bundle_with(fabrications)
    verdict = verify_bundle(bundle, archive=FakeArchive())

    assert verdict.verified == 1
    assert len(verdict.unsupported) == 50
    assert not verdict.failed
    assert verdict.accepted                      # the genuine record is genuine
    assert len(verdict.supported) == 1           # but only it is evidence

    with tempfile.TemporaryDirectory() as td:
        out = merge_bundle(bundle, into=Path(td), verdict=verdict)
        assert out["accepted"] == 1
        assert out["not_supported"] == 50
        written = json.loads(next(Path(td).glob("*.json")).read_text(encoding="utf-8"))
        assert {r["parameter"] for r in written["records"]} == {"BOD"}


def test_records_whose_page_cannot_be_fetched_are_not_merged():
    """The same thing happens by accident whenever archive.org is flaky
    mid-bundle. Unfetchable is not the same as true."""
    fabrications = [{"kind": "observation", "parameter": "lead", "value": 8.8,
                     "provenance": {"identifier": "nosuchitem", "page": 3,
                                    "source_text": "Lead was 8.8 mg/L."}}
                    for _ in range(20)]
    bundle = _bundle_with(fabrications)
    verdict = verify_bundle(bundle, archive=FakeArchive())
    assert len(verdict.unsupported) == 20
    assert len(verdict.supported) == 1


def test_a_claimed_number_the_sentence_never_states_fails():
    """Not "unchecked" -- failed. A sentence stating no number in digits or in
    words cannot be where a number came from; it was inferred elsewhere."""
    state, why = _value_in_quote(42.0, "The plant operated without incident.")
    assert state == "failed"
    assert "no number" in why


def test_a_record_with_no_value_is_still_kept():
    """A conclusion has no number to support, and refusing it would be a control
    stricter than the world."""
    state, _ = _value_in_quote(None, "No known health related guidelines were exceeded.")
    assert state == "unchecked"


# -- the filename ------------------------------------------------------------

@pytest.mark.parametrize("evil", [
    "/../brantford", "../../../pwned", "C:/Windows/Temp/pwned",
    "..\\..\\pwned", "a" * 300, "con", "x/y",
])
def test_a_sender_cannot_choose_where_the_file_lands(evil: str) -> None:
    """bundle_id names a file and arrives from the sender. "/../brantford"
    resolved to a write outside data/results, over any .json the process could
    reach, on a public endpoint."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        out = root / "results"
        out.mkdir()
        bundle = dict(make_bundle([GENUINE]), bundle_id=evil)
        verdict = verify_bundle(bundle, archive=FakeArchive())
        merge_bundle(bundle, into=out, verdict=verdict)

        landed = list(out.glob("*.json"))
        assert len(landed) == 1
        assert landed[0].resolve().parent == out.resolve()
        assert not list(root.glob("*.json")), "a file escaped the results directory"


def test_bundle_id_is_recomputed_not_trusted():
    """Two different bundles must not collide on one filename. bundle_id read
    the stored `key` field, which key-less records do not have, so every such
    bundle hashed to the sha256 of an empty string and overwrote the last."""
    from groundtruth.contribute import bundle_id

    other = dict(GENUINE, value=99.0, parameter="suspended solids")
    assert bundle_id([GENUINE]) != bundle_id([other])
    assert bundle_id([GENUINE]) == bundle_id([dict(GENUINE)])
