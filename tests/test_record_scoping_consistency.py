"""All result-file readers must agree on a record's place and identity."""

from __future__ import annotations

import json
from pathlib import Path

from concordance.contribute import Verdict, make_bundle, merge_bundle
from concordance.disputes import Claim, load_claims
from concordance.models import record_key
from concordance.tools import Corpus


def _raw_digesters_record() -> dict:
    return {
        "kind": "observation",
        "parameter": "BOD",
        "value": 12.0,
        "unit": "mg/L",
        "stream": "effluent",
        "place": "digesters",
        "facility": None,
        "period": "1969",
        "provenance": {
            "identifier": "brantford1969",
            "page": 1,
            "source_text": "The BOD reading was 12 mg/L.",
        },
    }


def _write_result(directory: Path) -> Path:
    path = directory / "brantford.json"
    path.write_text(
        json.dumps({
            "place": "Brantford",
            "model": "test",
            "n_records": 1,
            "records": [_raw_digesters_record()],
        }),
        encoding="utf-8",
    )
    return path


def test_corpus_ledger_and_export_share_one_scoped_record(tmp_path: Path) -> None:
    """A correction must contest the same slot that the portal displays."""
    path = _write_result(tmp_path)

    loaded = Corpus.load(path).records[0].to_dict()
    claim = load_claims(tmp_path)[0]

    assert loaded["place"] == claim.record["place"] == "Brantford"
    assert loaded["facility"] == claim.record["facility"] == "digesters"
    assert loaded["raw"]["reported_place"] == "digesters"
    assert claim.record["raw"]["reported_place"] == "digesters"
    assert record_key(loaded) == record_key(claim.record)
    assert Claim(record=loaded).slot == claim.slot


def test_share_style_raw_result_round_trip_does_not_duplicate(tmp_path: Path) -> None:
    """The records exported by ``share.py`` re-import as existing evidence."""
    _write_result(tmp_path)
    exported = [claim.record for claim in load_claims(tmp_path)]
    bundle = make_bundle(exported, contributor="same instance")
    verdict = Verdict(
        total=len(exported),
        verified=len(exported),
        supported=exported,
    )

    outcome = merge_bundle(bundle, into=tmp_path, verdict=verdict)

    assert outcome["accepted"] == 0
    assert outcome["duplicates_dropped"] == 1
    assert outcome["written"] is None
    assert len(Corpus.load_dir(tmp_path).records) == 1
