"""The prose extractor chooses archive terms before it invents new ones."""

from __future__ import annotations

import json

import concordance.extract as extraction
from concordance.models import PageText
from concordance.vocabulary import Term, Vocabulary, load


class CaptureClient:
    name = "test:capture"

    def __init__(self, response: list[dict[str, object]]) -> None:
        self.response = json.dumps(response)
        self.system = ""
        self.user = ""

    def complete(self, system: str, user: str) -> str:
        self.system = system
        self.user = user
        return self.response


def _page(source: str) -> PageText:
    return PageText(identifier="archive-item", page=7, text=source)


def _candidate(
    source: str,
    parameter: str,
    *,
    parameter_status: str,
    value: float = 1.0,
    unit: str = "count",
) -> dict[str, object]:
    return {
        "kind": "observation",
        "parameter": parameter,
        "parameter_status": parameter_status,
        "value": value,
        "unit": unit,
        "confidence": 0.9,
        "source_text": source,
    }


def test_document_title_selects_the_vocabulary_for_the_model(monkeypatch) -> None:
    vocab = Vocabulary(terms=[
        Term("mileage", "mileage", "distance", "transport", typical_units=("miles",)),
        Term("population", "population", "count", "population-economy"),
    ])
    seen_hints: list[str] = []
    render = vocab.for_prompt

    def record_hint(*, hint: str = "", limit: int = 240) -> str:
        seen_hints.append(hint)
        return render(hint=hint, limit=limit)

    monkeypatch.setattr(vocab, "for_prompt", record_hint)
    monkeypatch.setattr(extraction.vocabulary, "load", lambda: vocab)
    client = CaptureClient([])

    extraction.extract_prose(
        _page("Total mileage was 334.15 miles."),
        client=client,
        title="Canadian railway statistics",
        publisher="Dominion Bureau of Statistics",
    )

    assert seen_hints == ["Canadian railway statistics"]
    assert "--- BEGIN CONTROLLED VOCABULARY ---" in client.system
    assert "mileage  [miles]" in client.system
    assert 'set "parameter_status" to "proposed"' in client.system
    assert "share of national steel production" not in client.system
    assert "bus leasing share of budget" not in client.system


def test_known_alias_is_replaced_by_the_canonical_archive_term(monkeypatch) -> None:
    source = "There were 1,825 inhabitants."
    vocab = Vocabulary(terms=[
        Term("population", "population", "count", aliases=("inhabitants",)),
    ])
    monkeypatch.setattr(extraction.vocabulary, "load", lambda: vocab)
    client = CaptureClient([
        _candidate(source, "inhabitants", parameter_status="controlled",
                   value=1825, unit="persons"),
    ])

    result = extraction.extract_prose(_page(source), client=client, title="Census of Canada")

    assert result.kept == 1
    assert result.records[0].parameter == "population"
    assert result.records[0].raw["parameter_status"] == "controlled"
    assert result.records[0].raw["model_parameter_status"] == "controlled"
    assert result.records[0].raw["parameter_naming_version"] == (
        extraction.PARAMETER_NAMING_VERSION
    )
    assert result.records[0].raw["vocabulary_terms_available"] == 1


def test_unknown_term_remains_an_auditable_proposal(monkeypatch) -> None:
    source = "The rock seam was 12 metres wide."
    vocab = Vocabulary(terms=[Term("population", "population", "count")])
    monkeypatch.setattr(extraction.vocabulary, "load", lambda: vocab)
    client = CaptureClient([
        _candidate(source, "rock seam width", parameter_status="proposed",
                   value=12, unit="metres"),
    ])

    result = extraction.extract_prose(_page(source), client=client, title="Geological survey")

    assert result.kept == 1
    assert result.records[0].parameter == "rock seam width"
    assert result.records[0].raw["parameter_status"] == "proposed"
    assert result.records[0].raw["model_parameter_status"] == "proposed"


def test_missing_vocabulary_file_keeps_extraction_working(monkeypatch, tmp_path) -> None:
    source = "The average rent was $357 per month."
    absent = load(tmp_path / "not-built-yet.json")
    assert len(absent) == 0
    monkeypatch.setattr(extraction.vocabulary, "load", lambda: absent)
    client = CaptureClient([
        _candidate(source, "monthly rent", parameter_status="proposed",
                   value=357, unit="$/month"),
    ])

    result = extraction.extract_prose(_page(source), client=client, title="Housing report")

    assert result.kept == 1
    assert result.records[0].parameter == "monthly rent"
    assert result.records[0].raw["parameter_status"] == "proposed"
    assert "No controlled vocabulary is available" in client.system
    assert "Extraction must still\ncontinue" in client.system
    assert result.records[0].raw["vocabulary_terms_available"] == 0
