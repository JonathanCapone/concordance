"""The contribution directory is an add-only transactional record store."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from concordance.contribute import Verdict, bundle_id, make_bundle, merge_bundle
from concordance.tools import Corpus


def _record(name: str, value: float) -> dict:
    return {
        "kind": "observation",
        "parameter": name,
        "value": value,
        "unit": "mg/L",
        "stream": "effluent",
        "place": "Brantford",
        "period": "1969",
        "provenance": {
            "identifier": "brantford1969",
            "page": int(value),
            "source_text": f"The {name} reading was {value:g} mg/L.",
        },
    }


def _accepted(records: list[dict]) -> Verdict:
    return Verdict(total=len(records), verified=len(records), supported=records)


def test_overlapping_merges_are_one_scan_dedup_write_transaction(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Two request threads cannot both publish the record they share.

    Each thread is released together. The patched directory scan takes its
    snapshot before a second barrier: without the merge lock both snapshots are
    necessarily empty and the overlap is duplicated; with the lock, the first
    scan times out at the barrier, writes, and the second scan sees that write.
    This makes the old race deterministic rather than hoping the scheduler hits
    a narrow window.
    """
    one = _record("BOD", 12.0)
    shared = _record("suspended solids", 18.0)
    three = _record("phosphorus", 1.0)
    left = [one, shared]
    right = [shared, three]

    start = threading.Barrier(2)
    scan = threading.Barrier(2)
    original_glob = Path.glob

    def snapshot_glob(path: Path, pattern: str):
        snapshot = list(original_glob(path, pattern))
        if path.resolve() == tmp_path.resolve() and pattern == "*.json":
            try:
                scan.wait(timeout=0.2)
            except threading.BrokenBarrierError:
                pass
        return iter(snapshot)

    def submit(records: list[dict]):
        start.wait(timeout=2)
        bundle = make_bundle(records)
        return merge_bundle(bundle, into=tmp_path, verdict=_accepted(records))

    with monkeypatch.context() as patch:
        patch.setattr(Path, "glob", snapshot_glob)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(submit, left), pool.submit(submit, right)]
            outcomes = [future.result(timeout=5) for future in futures]

    assert sum(outcome["accepted"] for outcome in outcomes) == 3
    assert sum(outcome["duplicates_dropped"] for outcome in outcomes) == 1
    assert all(outcome["written"] for outcome in outcomes)

    corpus = Corpus.load_dir(tmp_path)
    keys = [record.key for record in corpus.records]
    assert len(keys) == 3
    assert len(set(keys)) == 3
    assert not list(tmp_path.glob("*.tmp"))


def test_an_occupied_bundle_filename_is_never_overwritten(tmp_path: Path) -> None:
    incoming = _record("BOD", 12.0)
    bundle = make_bundle([incoming])
    occupied = tmp_path / f"contributed-{bundle_id([incoming])}.json"
    existing = _record("suspended solids", 18.0)
    occupied.write_text(
        json.dumps({
            "place": "",
            "bundle_id": "an-earlier-accepted-contribution",
            "n_records": 1,
            "records": [existing],
        }),
        encoding="utf-8",
    )
    before = occupied.read_bytes()

    outcome = merge_bundle(bundle, into=tmp_path, verdict=_accepted([incoming]))

    assert outcome["accepted"] == 1
    assert Path(outcome["written"]) != occupied
    assert occupied.read_bytes() == before
    corpus = Corpus.load_dir(tmp_path)
    keys = [record.key for record in corpus.records]
    assert len(keys) == 2
    assert len(set(keys)) == 2
