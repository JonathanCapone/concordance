"""The archive's own words, and the matching that keeps them from fragmenting."""

from __future__ import annotations

import pytest

from concordance.vocabulary import Term, Vocabulary, load, normalise, save


def test_semantic_qualifiers_are_part_of_a_name() -> None:
    """Matching may forgive orthography, never words that alter identity.

    These pairs all occur in the evidence. Collapsing them before review merges
    observations with specifications, rates with totals, and extrema with the
    headline series -- three failures the project has already seen downstream.
    """
    dangerous_pairs = [
        ("population", "design population"),
        ("flow", "total flow"),
        ("average daily flow", "maximum daily flow"),
        ("flow", "per capita flow"),
        ("flow", "24 hour flow"),
        ("THMs", "total THMs"),
        ("operating cost", "total operating cost"),
    ]
    for left, right in dangerous_pairs:
        assert normalise(left) != normalise(right), (left, right)


def test_normalisation_is_orthographic_and_unicode_aware() -> None:
    assert normalise("Suspended-Solids") == normalise(" suspended  solids. ")
    assert normalise("ascorbic&#x2011;acid") == normalise("ASCORBIC ACID")
    assert normalise("épaisseur") != normalise("paisseur")


def test_matching_is_case_and_punctuation_blind() -> None:
    v = Vocabulary(terms=[Term("suspended solids", "suspended solids", "concentration")])
    for spelling in ("Suspended Solids", "suspended  solids", "SUSPENDED SOLIDS.",
                     "suspended-solids"):
        assert v.match(spelling) is not None, spelling


def test_an_alias_resolves_to_its_canonical_term() -> None:
    v = Vocabulary(terms=[Term("population", "population", "count",
                               aliases=("inhabitants", "number of persons"))])
    assert v.match("inhabitants").canonical == "population"
    assert v.match("Number of Persons").canonical == "population"


def test_an_unknown_name_is_reported_not_guessed() -> None:
    """The flag is the point: it is how a genuinely new term gets discovered
    instead of being silently mapped onto the nearest thing."""
    v = Vocabulary(terms=[Term("population", "population", "count")])
    assert v.match("width of strongly sheared rock") is None
    assert not v.is_known("cost estimate for one boiler at keith station")


def test_a_collision_is_visible() -> None:
    """Two entries claiming one name is a reconcile failure, and the vocabulary
    must be able to say so rather than resolving it by list order."""
    v = Vocabulary(terms=[Term("population", "population", "count"),
                          Term("residents", "population", "count",
                               aliases=("population",))])
    assert v.collisions()


def test_an_absent_vocabulary_is_not_an_error() -> None:
    """A clone with no curated file must still run; the extractor falls back to
    naming freely, which is what it did before this existed."""
    v = load("data/vocabulary/does-not-exist.json")
    assert len(v) == 0
    assert v.match("anything") is None


def test_the_prompt_list_leads_with_what_the_document_is_about() -> None:
    terms = [
        Term("population", "population", "count", "population-economy",
             readings_covered=45),
        Term("dustfall", "dustfall", "rate", "air-emissions", readings_covered=3),
    ]
    listing = Vocabulary(terms=terms).for_prompt(hint="Ontario air pollution survey")
    assert "dustfall" in listing and "population" in listing


def test_entries_are_unreviewed_until_somebody_says_otherwise() -> None:
    """The machine proposes; a person confirms. Published output has to be able
    to say which entries have been looked at."""
    v = Vocabulary(terms=[Term("population", "population", "count")])
    assert v.unreviewed() == v.terms


def test_save_refuses_colliding_or_half_resolved_entries(tmp_path) -> None:
    colliding = Vocabulary(terms=[
        Term("total-flow", "flow", "total"),
        Term("total flow", "flow", "rate"),
    ])
    with pytest.raises(ValueError, match="matching key"):
        save(colliding, tmp_path / "collision.json")

    half_resolved = Vocabulary(terms=[Term("mileage", "mileage", "")])
    with pytest.raises(ValueError, match="both be set or both be empty"):
        save(half_resolved, tmp_path / "half.json")
