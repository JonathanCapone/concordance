"""The provisional builder admits evidence without deciding what it means."""

from __future__ import annotations

import json

import pytest

from scripts.build_vocabulary import (
    build_vocabulary,
    is_attested,
    read_sources,
    validate_output,
)
from concordance.vocabulary import save


def _record(parameter, quote, *, unit="persons", kind="observation"):
    return {
        "kind": kind,
        "parameter": parameter,
        "value": 1,
        "unit": unit,
        "provenance": {"source_text": quote, "identifier": "fixture", "page": 1},
    }


def _result(records):
    return {
        "place": "Fixture",
        "model": "fixture",
        "n_records": len(records),
        "pages_attempted": [],
        "records": records,
    }


def test_attestation_is_a_complete_orthographic_phrase() -> None:
    assert is_attested("ascorbic acid", "The ascorbic-acid value was 18 mg.")
    assert is_attested("débit total", "DÉBIT   TOTAL : 40 litres")
    assert not is_attested("gas", "The gasoline volume was 40 litres.")
    assert not is_attested("steel production share", "50 per cent of all steel produced")


def test_builder_preserves_identity_words_and_only_adds_orthographic_aliases() -> None:
    payload = _result([
        _record("population", "The population was 10,000.", unit="persons"),
        _record("design population", "Design population: 20,000.", unit="persons",
                kind="design"),
        _record("total-flow", "The total-flow was 40 million gallons.",
                unit="million gallons"),
        _record("total flow", "Total flow was 41 million gallons.",
                unit="million gallons"),
        _record("total flow", "Total flow was 42 million gallons.",
                unit="million gallons"),
    ])
    vocab, stats = build_vocabulary([("fixture.json", payload)])

    assert stats.terms_built == 3
    assert vocab.match("population").canonical == "population"
    assert vocab.match("design population").canonical == "design population"
    total = vocab.match("total flow")
    assert total.canonical == "total flow"
    assert total.aliases == ("total-flow",)
    assert total.readings_covered == 3
    assert not total.reviewed
    assert not vocab.collisions()


def test_unattested_names_and_conclusions_are_excluded() -> None:
    payload = _result([
        _record("bus leasing share of budget", "Leasing runs to 7 per cent."),
        _record("water quality", "Water quality was acceptable.", kind="conclusion",
                unit=None),
        _record("temperature", "The temperature was 18 degrees.", unit="degrees F"),
    ])
    vocab, stats = build_vocabulary([("fixture.json", payload)])

    assert [term.canonical for term in vocab.terms] == ["temperature"]
    assert stats.records_excluded_unattested == 1
    assert stats.records_excluded_wrong_kind == 1


def test_disagreeing_record_level_resolutions_leave_identity_blank() -> None:
    payload = _result([
        _record("BOD", "BOD was 30 mg/L.", unit="mg/L"),
        _record("BOD", "BOD was 3,600 pounds.", unit="pounds"),
    ])
    vocab, _ = build_vocabulary([("fixture.json", payload)])
    bod = vocab.match("BOD")
    assert bod is not None
    assert bod.substance == ""
    assert bod.measure == ""


def test_stratified_aggregate_proves_a_name_but_not_its_identity() -> None:
    coverage = {
        "archive_language": {},
        "model_language": {},
        "controls": {},
        "stopping_rule": {},
        "terms": [{
            "term": "ascorbic acid",
            "archive_language": True,
            "verbatim_sightings": 3,
            "suspect_ocr": False,
            "written_as": ["ascorbic acid content", "ascorbic-acid value"],
            "units": [["mg", 3]],
            "example": "The ascorbic-acid value was 18 mg.",
        }],
    }
    vocab, stats = build_vocabulary([("coverage.json", coverage)])

    assert stats.coverage_terms_attested == 1
    term = vocab.terms[0]
    assert term.canonical == "ascorbic-acid value"
    assert term.readings_covered == 3
    assert term.typical_units == ("mg",)
    assert term.substance == term.measure == ""
    assert term.reviewed is False


def test_saved_output_round_trips_and_validates(tmp_path) -> None:
    vocab, _ = build_vocabulary([("fixture.json", _result([
        _record("population", "Population 100.", unit="persons"),
    ]))])
    path = save(vocab, tmp_path / "vocabulary.json", note="fixture")
    loaded, envelope = validate_output(path)
    assert len(loaded) == envelope["n_terms"] == 1

    envelope["n_terms"] = 99
    path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(ValueError, match="n_terms"):
        validate_output(path)

    envelope["n_terms"] = 1
    envelope["terms"][0]["reviewed"] = "false"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(ValueError, match="reviewed must be true or false"):
        validate_output(path)


def test_worktree_mode_requires_explicit_inputs() -> None:
    with pytest.raises(ValueError, match="requires"):
        read_sources(worktree=True)


def test_output_envelope_rejects_boolean_counts_and_nontext_note(tmp_path) -> None:
    vocab, _ = build_vocabulary([("fixture.json", _result([
        _record("population", "Population 100.", unit="persons"),
    ]))])
    path = save(vocab, tmp_path / "vocabulary.json", note="fixture")
    envelope = json.loads(path.read_text(encoding="utf-8"))

    envelope["version"] = True
    path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(ValueError, match="version must be 1"):
        validate_output(path)

    envelope["version"] = 1
    envelope["n_terms"] = True
    path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(ValueError, match="n_terms"):
        validate_output(path)

    envelope["n_terms"] = 1
    envelope["note"] = ["not", "text"]
    path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(ValueError, match="note must be a string"):
        validate_output(path)
