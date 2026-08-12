"""A reading's identity must be a function of the reading, not a stored string.

The bug these guard against: `data/results/*.json` carries a `key` field written
before later normalisation, so it no longer matches its own contents. Dedup
compared a live key against those stale ones, never matched, and re-added every
record on every import -- so pushing an instance its own library merged 19 of 20
readings as new. In a project whose whole distribution model is round trips,
that doubles the dataset each lap.
"""

from __future__ import annotations

import json
from pathlib import Path

from groundtruth.contribute import make_bundle, merge_bundle, Verdict
from groundtruth.models import record_key
from groundtruth.tools import Corpus

RESULTS = Path("data/results")


def _accepted(n: int) -> Verdict:
    """A passing verdict. Verification itself is tested in test_contribute."""
    return Verdict(total=n, verified=n)


def test_stored_keys_are_not_trusted_for_identity() -> None:
    """The stored `key` field is stale on disk. This is the fact that bit us."""
    stored, live = set(), {r.key for r in Corpus.load_dir(RESULTS).records}
    for f in RESULTS.glob("*.json"):
        for r in json.loads(f.read_text(encoding="utf-8")).get("records") or []:
            if r.get("key"):
                stored.add(r["key"])
    assert stored, "no stored keys to check"
    # Not asserting they are ALL stale -- asserting that trusting them is unsafe,
    # which is true as long as the overlap is poor. If a future change makes the
    # stored field accurate, this test should be deleted deliberately, not
    # silently satisfied.
    assert len(stored & live) < len(live) / 2


def test_recomputed_key_matches_the_loaded_record() -> None:
    """Recomputing from the stored dict agrees with the record the corpus built."""
    live = {r.key for r in Corpus.load_dir(RESULTS).records}
    agree = 0
    total = 0
    for f in RESULTS.glob("*.json"):
        payload = json.loads(f.read_text(encoding="utf-8"))
        place = payload.get("place")
        for r in payload.get("records") or []:
            if not r.get("place") and place:
                r = dict(r, place=place)
            total += 1
            if record_key(r) in live:
                agree += 1
    assert total and agree / total > 0.9, f"only {agree}/{total} recompute correctly"


def test_reimporting_the_library_adds_nothing(tmp_path: Path) -> None:
    """The round trip that was silently doubling the dataset."""
    records = [r.to_dict() for r in Corpus.load_dir(RESULTS).records]
    assert records

    for f in RESULTS.glob("*.json"):
        (tmp_path / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")

    bundle = make_bundle(records, contributor="the same instance")
    out = merge_bundle(bundle, into=tmp_path, verdict=_accepted(len(records)))
    assert out["accepted"] == 0, f"re-import added {out['accepted']} records"
    assert out["duplicates_dropped"] == len(records)


def test_a_bundle_that_repeats_itself_lands_once(tmp_path: Path) -> None:
    records = [r.to_dict() for r in Corpus.load_dir(RESULTS).records][:5]
    bundle = make_bundle(records + records, contributor="someone who concatenated")
    out = merge_bundle(bundle, into=tmp_path, verdict=_accepted(10))
    assert out["accepted"] == 5


def test_a_note_does_not_become_a_place(tmp_path: Path) -> None:
    """Corpus.load treats the file's `place` as a default for placeless records."""
    rec = {"kind": "observation", "parameter": "BOD", "value": 12.0, "unit": "mg/L",
           "provenance": {"identifier": "x", "page": 1, "source_text": "BOD was 12 mg/L."}}
    bundle = make_bundle([rec], note="readings from Fergus, checked by hand")
    merge_bundle(bundle, into=tmp_path, verdict=_accepted(1))
    loaded = Corpus.load(*tmp_path.glob("*.json"))
    assert loaded.records
    assert loaded.records[0].place != "readings from Fergus, checked by hand"
