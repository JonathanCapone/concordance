"""Which year a sentence attaches to a number, when it names two.

Reports constantly compare a year to the one before it, and state both numbers
in one sentence. The extractor is usually right about which is which -- it was
right about thirteen of the fourteen in this corpus -- and the fourteenth was
Brantford's headline: "The average BOD removal efficiency was 94% in 1969
compared with only 89% in 1968" filed BOTH values under 1969, so the town's
published series read 89% for a year whose page says 94%.

The danger in fixing that is obvious and is what most of these tests are for. A
repair that also rewrites the thirteen correct records is worse than the bug,
because it would move numbers that were right and leave the same kind of trace.
So the rule abstains unless the question is genuinely ambiguous AND decidable,
and `test_it_agrees_with_the_extractor_where_the_extractor_is_right` is the one
that matters.
"""

from __future__ import annotations

import pytest

from concordance.dating import year_for_reading

# Real sentences from the corpus, with the year each value belongs to.
COMPARATIVE = [
    ("During 1963 the average daily flow was 5. 59 as compared to 5. 67 "
     "million gallons per day in 1962.", 5.59, 1963),
    ("During 1963 the average daily flow was 5. 59 as compared to 5. 67 "
     "million gallons per day in 1962.", 5.67, 1962),
    ("During 1964 the average daily flow was 6. 07 as compared to 5. 59 "
     "million gallons per day in 1963.", 6.07, 1964),
    ("During 1964 the average daily flow was 6. 07 as compared to 5. 59 "
     "million gallons per day in 1963.", 5.59, 1963),
    ("The average BOD removal efficiency was 94% in 1969 compared with only "
     "89% in 1968.", 94.0, 1969),
    ("The average BOD removal efficiency was 94% in 1969 compared with only "
     "89% in 1968.", 89.0, 1968),
    ("Phosphorus concentrations in the plant effluent averaged 5. 1 mg/1 in "
     "1972 as compared to 4. 3 mg/1 during 1971.", 5.1, 1972),
    ("Phosphorus concentrations in the plant effluent averaged 5. 1 mg/1 in "
     "1972 as compared to 4. 3 mg/1 during 1971.", 4.3, 1971),
]


@pytest.mark.parametrize("quote,value,expected", COMPARATIVE)
def test_the_nearest_year_is_the_right_year(quote: str, value: float,
                                            expected: int) -> None:
    assert year_for_reading(quote, value) == expected


def test_it_agrees_with_the_extractor_where_the_extractor_is_right() -> None:
    """The test that licenses running this over the whole dataset.

    Six of the eight cases above are records the extractor already filed
    correctly. If the rule disagreed with any of them it would be moving good
    data, and it would have to be thrown away no matter how well it fixed the
    seventh.
    """
    for quote, value, expected in COMPARATIVE:
        assert year_for_reading(quote, value) == expected


# -- when it must abstain ---------------------------------------------------

def test_a_year_range_is_not_a_comparison() -> None:
    """"between 1961 and 1969" names two years and compares nothing."""
    assert year_for_reading("The plant operated between 1961 and 1969 "
                            "without incident, treating 5. 0 million gallons.",
                            5.0) is None


def test_one_year_needs_no_disambiguating() -> None:
    assert year_for_reading("The average flow in 1969 was 3. 2 million "
                            "gallons.", 3.2) is None


def test_a_value_stated_twice_is_a_coin_toss() -> None:
    """Nearest-year is only meaningful if the number appears once."""
    assert year_for_reading("Flow was 5. 0 in 1968 compared with 5. 0 in 1967.",
                            5.0) is None


def test_a_value_not_in_the_sentence_gives_nothing_to_measure_from() -> None:
    assert year_for_reading("Flow rose in 1969 compared with 1968.", 7.7) is None


def test_no_value_and_no_quote_abstain() -> None:
    assert year_for_reading("Anything at all in 1969 compared with 1968.", None) is None
    assert year_for_reading("", 5.0) is None


def test_a_four_digit_quantity_is_not_a_year() -> None:
    """This corpus says "1475 million gallons" and "2600 lb/day"; reading those
    as dates would invent comparisons that are not on the page."""
    assert year_for_reading("The plant treated 1475 million gallons at a cost "
                            "of 2600 dollars, compared with less before.",
                            1475) is None


def test_a_value_is_never_matched_against_a_year_it_equals() -> None:
    """Looking for "1968" as a value must not find the DATE 1968 and measure a
    distance of zero to itself, which would file the reading under whichever
    year it numerically happens to equal.

    The consequence of abstaining here is that a genuine reading of "1968 tons"
    in a comparative sentence keeps the extractor's year. That is the right
    trade: the extractor is usually right, and this rule exists only to catch
    the case where the sentence plainly disagrees with it.
    """
    assert year_for_reading("Flow rose in 1969 compared with 1968.", 1968) is None
    assert year_for_reading("Output was 1968 tons in 1972 compared with 1971.",
                            1968) is None
