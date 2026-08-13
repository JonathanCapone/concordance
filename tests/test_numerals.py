"""Numbers the archive wrote in words.

The motivating record is real: a Brantford bundle carried "Just over three
million gallons", a correct reading of a correct sentence, and verification
could only shrug at it -- the sentence has no digits, so the check returned
"unchecked" rather than "true". That is an honest answer and a lost measurement.

The risk running the other way is worse and is what most of these tests guard.
If spelled-out numbers count as evidence naively, then "one of the plants was
closed" states the value 1, and anyone could attach the value 1 to any sentence
containing the word "one" and have it verify. So the door is deliberately
narrow: a phrase must carry a magnitude word, or be followed by a unit, or be
large enough that nobody writes it by accident.
"""

from __future__ import annotations

import pytest

from concordance.numerals import (
    quantities_in,
    scan,
    states_value,
    words_to_number,
)


@pytest.mark.parametrize("phrase,expected", [
    # English
    ("three million", 3_000_000),
    ("forty-two thousand", 42_000),
    ("twenty-two", 22),
    ("one hundred and fifty", 150),
    ("three hundred thousand", 300_000),
    ("a million", 1_000_000),
    ("nineteen", 19),
    ("two hundred", 200),
    # Halves, which arrive on either side of their magnitude.
    ("half a million", 500_000),
    ("two and a half million", 2_500_000),
    ("a million and a half", 1_500_000),
    ("three and a half thousand", 3_500),
    # French, because a third of this corpus is bilingual.
    ("deux millions", 2_000_000),
    ("trois mille", 3_000),
    ("cent cinquante", 150),
    ("un million et demi", 1_500_000),
    ("deux millions et demi", 2_500_000),
    # French builds 70/80/90 out of 60 and 20, which a plain accumulator gets
    # wrong: quatre-vingt-dix would be 4 + 20 + 10 = 34.
    ("soixante-dix", 70),
    ("quatre-vingts", 80),
    ("quatre-vingt-dix", 90),
])
def test_spelled_numbers_parse(phrase: str, expected: float) -> None:
    assert words_to_number(phrase) == expected


@pytest.mark.parametrize("phrase", [
    "the digesters", "of the", "plant capacity", "", "sludge was pumped",
])
def test_prose_is_not_a_number(phrase: str) -> None:
    assert words_to_number(phrase) is None


def test_the_motivating_sentence() -> None:
    """The reading that could not be verified before this module existed."""
    sentence = ("Just over three million gallons of raw sludge was pumped to "
                "the digesters.")
    found = scan(sentence)
    assert len(found) == 1
    n = found[0]
    assert n.value == 3_000_000
    assert n.has_magnitude
    assert n.qualifier == "over"          # "just over" is not "exactly"
    assert n.looks_like_a_quantity
    assert states_value(sentence, 3_000_000)


def test_a_bare_article_is_not_evidence() -> None:
    """The failure mode that would make this module a liability."""
    text = "one of the plants was closed"
    assert words_to_number("one") == 1        # the parser still reads it
    assert not quantities_in(text)            # but it is not a quantity
    assert states_value(text, 1) is None      # and it proves nothing


def test_a_unit_after_the_word_makes_it_a_quantity() -> None:
    assert states_value("nine samples were taken", 9)
    assert states_value("six feet of head loss", 6)
    assert states_value("twenty-two samples were taken", 22)


def test_a_large_spelled_number_stands_on_its_own() -> None:
    """Nobody writes "forty-two" by accident the way they write "one"."""
    assert states_value("forty-two were rejected", 42)


def test_the_longest_phrase_wins() -> None:
    """"three million" must not also yield a bare 3."""
    values = [n.value for n in scan("three million gallons")]
    assert values == [3_000_000]


def test_rounding_is_allowed_but_only_slightly() -> None:
    """A reader who writes 3,000,000 for "just over three million" is right.
    One who writes 4,000,000 is not."""
    sentence = "Just over three million gallons"
    assert states_value(sentence, 3_000_000)
    assert states_value(sentence, 3_050_000)      # within 2%
    assert states_value(sentence, 4_000_000) is None


def test_several_numbers_in_one_sentence() -> None:
    found = scan("The plant serves forty thousand people and treats "
                 "two million gallons daily.")
    assert [n.value for n in found] == [40_000, 2_000_000]


def test_qualifiers_are_recorded_not_discarded() -> None:
    """"approximately three million" and "three million" are different claims,
    and Record has a qualifier field so the difference survives."""
    assert scan("approximately three million gallons")[0].qualifier == "approximate"
    assert scan("nearly two thousand residents")[0].qualifier == "under"
    assert scan("more than five hundred samples")[0].qualifier == "over"
    assert scan("three million gallons")[0].qualifier is None
