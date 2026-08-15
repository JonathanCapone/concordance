"""The circumstance a sentence attaches to its value, held to the value's rules.

"Flows exceeded 7.2 mgd 10 percent of the time" and "5.6 mgd 50 percent of the
time" are one distribution read at two points, not the archive disagreeing with
itself -- yet 84 ledger slots were manufactured disagreements of exactly this
shape, because the record had nowhere to put the circumstance.

The field is dangerous in a way no other field is: it changes a record's
identity without being a fact about the measurement. Every property below
exists to keep that from becoming a way to lie:

  * absent must hash exactly as before the field existed (the 88-record lesson)
  * present must split identities (or merge dedup destroys same-value twins)
  * ungrounded must be stripped before identity exists (or one true sentence
    mints unlimited distinct verified claims)
  * every loader must carry it (or the two sides of a round trip disagree)
"""

from __future__ import annotations

import json
from pathlib import Path

from concordance.contribute import (
    condition_in_quote, ground_condition, make_bundle, merge_bundle,
    public_record_key, record_problems, verify_bundle,
)
from concordance.disputes import Claim, resolve, slot_of
from concordance.models import Record, record_key


QUOTE = "Twice the design flow of 3.0 mgd was received 83 percent of the time."

_EXCEEDANCE = ("The flows exceeded approximately 7.2 mgd 10 percent of the time "
               "and approximately 5.6 mgd 50 percent of the time.")
_PUMPS = "One pump rated 150 USgpm duty and one rated 150 USgpm standby."


class _FakeArchive:
    """Serves the fixture pages; stands in for the network."""

    PAGES = {"owensound": {7: QUOTE + " " + _EXCEEDANCE + " " + _PUMPS}}

    def pages(self, identifier, **_):
        class P:
            def __init__(self, page, text):
                self.page, self.text = page, text
        return [P(p, t) for p, t in self.PAGES.get(identifier, {}).items()]


def _rec(**over) -> dict:
    base = {
        "kind": "observation", "parameter": "flow frequency", "value": 3.0,
        "unit": "mgd", "stream": "unknown", "place": "Owen Sound",
        "facility": "sewage plant", "period": "1969",
        "provenance": {"identifier": "owensound", "page": 7,
                       "source_text": QUOTE},
    }
    base.update(over)
    return base


# -- identity: absent is byte-identical, present splits -----------------------

def test_a_record_without_condition_keys_exactly_as_it_always_did() -> None:
    """All 6,000+ stored records lack the field. If absence changed the hash,
    every one would re-import as new on the next round trip -- the 88-record
    bug at full scale."""
    plain = _rec()
    assert record_key(plain) == record_key(dict(plain, condition=None))
    assert record_key(plain) == record_key(dict(plain, condition=""))
    assert public_record_key(plain) == public_record_key(dict(plain, condition=None))


def test_two_values_under_different_conditions_are_different_records() -> None:
    """The refuted design put condition in slot identity only. Same-value
    twins -- duty and standby pumps both rated 150 USgpm -- then shared one
    public_record_key and merge dedup silently destroyed the second before
    slot identity ever saw it."""
    duty = _rec(condition="duty")
    standby = _rec(condition="standby")
    assert record_key(duty) != record_key(standby)
    assert record_key(duty) != record_key(_rec())
    assert slot_of(duty) != slot_of(standby)


def test_two_claims_differing_only_in_condition_occupy_two_slots() -> None:
    q = _EXCEEDANCE
    a = _rec(value=7.2, condition="10 percent of the time",
             provenance={"identifier": "owensound", "page": 7, "source_text": q})
    b = _rec(value=5.6, condition="50 percent of the time",
             provenance={"identifier": "owensound", "page": 7, "source_text": q})
    assert slot_of(a) != slot_of(b)
    ledger = resolve([Claim(record=a), Claim(record=b)], archive=_FakeArchive())
    states = {s.state for s in ledger.slots.values()}
    assert len(ledger.slots) == 2
    assert "contested" not in states and "undistinguished" not in states


# -- grounding: the words must be in the sentence -----------------------------

def test_a_condition_the_sentence_states_survives() -> None:
    r = ground_condition(_rec(condition="83 percent of the time"))
    assert r["condition"] == "83 percent of the time"


def test_a_condition_the_sentence_does_not_state_is_stripped() -> None:
    """Stripped, not rejected: a wrong condition is an annotation failure, not
    a fabricated measurement. And stripping collapses the identity back, which
    is what defuses the minting attack."""
    poisoned = _rec(condition="under emergency bypass")
    cleaned = ground_condition(poisoned)
    assert "condition" not in cleaned
    assert public_record_key(cleaned) == public_record_key(_rec())


def test_token_containment_not_substring() -> None:
    assert condition_in_quote("83 percent", QUOTE)
    assert not condition_in_quote("each", "The beaches were closed all summer.")
    assert not condition_in_quote("3.0", "The value 30 appears here.")


def test_a_fabricated_condition_cannot_mint_a_new_identity_through_merge(
        tmp_path: Path) -> None:
    """One true sentence, resubmitted with an invented circumstance, must land
    as the duplicate it is -- not as a second verified record."""
    true_record = _rec()
    (tmp_path / "owensound.json").write_text(json.dumps({
        "place": "Owen Sound", "records": [true_record]}), encoding="utf-8")

    poisoned = _rec(condition="during the spring flood")
    bundle = make_bundle([poisoned], contributor="attacker")
    verdict = verify_bundle(bundle, archive=_FakeArchive())
    out = merge_bundle(bundle, into=tmp_path, verdict=verdict)
    assert out["accepted"] == 0, "a fabricated condition minted a new record"


def test_grounded_same_value_twins_both_survive_merge(tmp_path: Path) -> None:
    """The flip side: two real readings equal in every keyed field except the
    circumstance the sentence itself states must BOTH reach disk."""
    q = _PUMPS
    twins = [
        _rec(value=150.0, unit="USgpm", parameter="pump capacity",
             condition="duty",
             provenance={"identifier": "owensound", "page": 7, "source_text": q}),
        _rec(value=150.0, unit="USgpm", parameter="pump capacity",
             condition="standby",
             provenance={"identifier": "owensound", "page": 7, "source_text": q}),
    ]
    bundle = make_bundle(twins, contributor="reader")
    verdict = verify_bundle(bundle, archive=_FakeArchive())
    out = merge_bundle(bundle, into=tmp_path, verdict=verdict)
    assert out["accepted"] == 2, "merge dedup destroyed a same-value twin"


# -- every loader carries it --------------------------------------------------

def test_the_loaders_do_not_drop_the_field(tmp_path: Path) -> None:
    """Corpus.load and record_problems rebuild records from explicit kwarg
    lists. Either one dropping condition recreates the loader asymmetry that
    re-imported the library's own data as 88 new records."""
    from concordance.tools import Corpus

    stored = _rec(condition="83 percent of the time")
    (tmp_path / "owensound.json").write_text(json.dumps({
        "place": "Owen Sound", "records": [stored]}), encoding="utf-8")
    loaded = Corpus.load(tmp_path / "owensound.json").records
    assert loaded[0].condition == "83 percent of the time"
    assert record_key(loaded[0].to_dict()) == record_key(stored)

    assert record_problems(stored) == []
    assert Record(kind="observation", parameter="x",
                  condition="y").to_dict()["condition"] == "y"


def test_a_non_string_condition_is_rejected_at_the_boundary() -> None:
    assert any("condition" in p for p in record_problems(_rec(condition=7)))
    assert any("condition" in p for p in record_problems(_rec(condition={"a": 1})))
    assert any("condition" in p for p in record_problems(_rec(condition="x" * 201)))


# -- the prompt asks for it ---------------------------------------------------

def test_the_extraction_prompt_teaches_the_field_and_the_headings() -> None:
    from concordance.extract import SYSTEM

    assert '"condition"' in SYSTEM
    assert "heading" in SYSTEM
    # The rule that makes it safe travels with the request for it.
    assert "source_text" in SYSTEM


def test_the_place_page_renders_the_condition() -> None:
    import concordance.portal as portal
    import concordance.server as server_mod

    page_source = Path(portal.__file__).read_text(encoding="utf-8")
    assert "x.condition" in page_source
    server_source = Path(server_mod.__file__).read_text(encoding="utf-8")
    assert '"condition": r.condition' in server_source
