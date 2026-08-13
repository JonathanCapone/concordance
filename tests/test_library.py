"""Failure-path tests for reading a place into the shared library."""

from __future__ import annotations

from types import SimpleNamespace

from concordance import extract, library


def test_reading_zero_records_is_empty_and_keeps_nothing(tmp_path, monkeypatch):
    class FakeArchive:
        def iter_items(self, *, title_contains):
            assert title_contains == "nowhere"
            return iter([{
                "identifier": "empty-report",
                "title": "Nowhere annual report",
                "year": "1970",
            }])

        def pages(self, identifier):
            assert identifier == "empty-report"
            return [SimpleNamespace(identifier=identifier, page=1)]

    class FakeClient:
        def __init__(self, model):
            self.name = f"fake:{model}"

    def no_records(page, **kwargs):
        return SimpleNamespace(records=[])

    def verification_must_not_run(*args, **kwargs):
        raise AssertionError("an empty extraction is not a contribution")

    destination = tmp_path / "library"
    monkeypatch.setattr(library, "LIBRARY", destination)
    monkeypatch.setattr(library, "Archive", FakeArchive)
    monkeypatch.setattr(extract, "OllamaClient", FakeClient)
    monkeypatch.setattr(
        library,
        "route",
        lambda page: SimpleNamespace(paths={library.RPath.PROSE}),
    )
    monkeypatch.setattr(library, "verify_bundle", verification_must_not_run)

    answer = library.ask("Nowhere", extractor=no_records)

    assert answer.source == "empty"
    assert answer.records == []
    assert answer.documents == 1
    assert answer.verified == 0
    assert not answer.contributed
    assert not destination.exists()
    assert "Nothing found" in answer.describe()
    assert "nothing was added to the library" in answer.describe()
    assert "in the library now" not in answer.describe()


def test_an_unshared_read_is_described_as_unshared():
    answer = library.Answer(
        query="Somewhere",
        records=[{"value": 1}],
        source="read now",
        documents=1,
        contributed=False,
    )

    assert "not added to the library" in answer.describe()
    assert "in the library now" not in answer.describe()
