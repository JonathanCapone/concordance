"""The file-transfer CLI must keep only the verifier's positive record set."""

from __future__ import annotations

import argparse
import json

from concordance.contribute import Verdict, make_bundle
from scripts import share


def _record(parameter: str, value: float) -> dict:
    return {
        "kind": "observation",
        "parameter": parameter,
        "value": value,
        "unit": "mg/L",
        "provenance": {
            "identifier": "item1",
            "page": 1,
            "source_text": f"The {parameter} result was {value:g} mg/L.",
        },
    }


def test_verified_only_import_uses_positive_supported_set(monkeypatch, tmp_path):
    """A failed record must not make an unsupported table claim look verified.

    The old CLI reconstructed the subset as ``everything not failed``. That
    retained unsupported evidence and could merge it beside one genuine record.
    """
    good = _record("BOD", 41.2)
    failed = _record("lead", 9.0)
    unsupported = _record("table value", 99.0)
    source = make_bundle([good, failed, unsupported], contributor="stranger")
    path = tmp_path / "incoming.json"
    path.write_text(json.dumps(source), encoding="utf-8")

    first = Verdict(
        total=3,
        verified=1,
        failed=[{"why": "wrong number"}],
        unsupported=[{"why": "no localized cell evidence"}],
        supported=[good],
    )
    second = Verdict(total=1, verified=1, supported=[good])
    verdicts = iter((first, second))
    monkeypatch.setattr(share, "verify_bundle", lambda *a, **k: next(verdicts))

    merged: dict = {}

    def fake_merge(bundle, *, into, verdict):
        merged.update(bundle)
        assert verdict is second
        return {"accepted": 1, "duplicates_dropped": 0}

    monkeypatch.setattr(share, "merge_bundle", fake_merge)
    args = argparse.Namespace(
        bundle=str(path),
        into=str(tmp_path / "results"),
        dry_run=False,
        verified_only=True,
    )

    assert share.do_import(args) == 0
    assert merged["records"] == [good]
    assert merged["n_records"] == 1
    assert merged["bundle_id"] == make_bundle([good])["bundle_id"]
