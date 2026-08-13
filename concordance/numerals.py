"""Numbers the archive wrote out in words.

The corpus states measurements in prose, and prose does not always use digits:

    "Just over three million gallons of raw sludge was pumped to the digesters."
    "The plant serves a population of forty-two thousand."
    "Le debit moyen etait de deux millions et demi de gallons."

Every one of those is a measurement, and every one of them is currently
invisible. The extractor finds nothing because it looks for digits, and the
verifier gives up: `_value_in_quote` returns "unchecked -- value is written in
words, not digits", which is the honest answer available to a check that cannot
read words. This module is what makes a better answer available.

Two callers, with opposite risk profiles, which is why the scanner reports more
than a number:

* **Extraction** wants recall, and can afford to propose a reading that the
  verifier then throws out.
* **Verification** must not get looser. If "one" in "one of the plants was
  closed" counted as the value 1, anybody could attach the value 1 to any
  sentence containing the word "one" and have it verify. So `scan` reports
  whether a phrase carried a magnitude word ("three MILLION") and what followed
  it, and the verifier requires one of those before believing a spelled-out
  number. A bare "one" proves nothing and is treated that way.

Both languages, because a third of this corpus is bilingual and Statistics
Canada prints both columns on the same page.

**What this deliberately does not do.** Fractions other than "half", ordinals,
and numbers spelled across a line break are not handled. Each of those is a
real gap and it is better to name them than to half-implement them: a parser
that returns a confident wrong number is worse here than one that returns
nothing, because the wrong number would be published with a citation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Words worth a value on their own.
_UNITS: dict[str, float] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,

    # French. "quatre-vingt" is handled before tokenising, since 4 x 20 does not
    # fall out of an accumulator that only ever adds.
    "zero_fr": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4,
    "cinq": 5, "six_fr": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
    "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15,
    "seize": 16, "vingt": 20, "vingts": 20, "trente": 30, "quarante": 40,
    "cinquante": 50, "soixante": 60,
}

#: Multipliers that scale what came before them.
_SCALE: dict[str, float] = {
    "hundred": 100, "hundreds": 100,
    "thousand": 1_000, "thousands": 1_000,
    "million": 1_000_000, "millions": 1_000_000,
    "billion": 1_000_000_000, "billions": 1_000_000_000,

    "cent": 100, "cents": 100,
    "mille": 1_000, "milles": 1_000,
    "milliard": 1_000_000_000, "milliards": 1_000_000_000,
}

#: Scale words big enough that a spelled-out number carrying one is almost
#: certainly a quantity rather than a stray article. "three million gallons" is
#: a measurement; "one plant" is a sentence.
_MAGNITUDE = {"hundred", "hundreds", "thousand", "thousands", "million",
              "millions", "billion", "billions", "cent", "cents", "mille",
              "milles", "milliard", "milliards"}

#: Joiners that may appear inside a number phrase without ending it.
_GLUE = {"and", "et", "a", "an", "of", "de", "des", "du"}

#: "half a million", "two and a half million".
_HALF = {"half", "demi", "demie"}

#: Words that qualify a number without changing it. Recorded, not discarded --
#: "just over three million" is a different claim from "three million", and the
#: record has a `qualifier` field precisely so that difference survives.
_QUALIFIERS: dict[str, str] = {
    "just over": "over", "just under": "under", "slightly over": "over",
    "slightly under": "under", "a little over": "over", "well over": "over",
    "more than": "over", "over": "over", "in excess of": "over",
    "less than": "under", "under": "under", "nearly": "under",
    "almost": "under", "close to": "approximate",
    "about": "approximate", "approximately": "approximate", "some": "approximate",
    "around": "approximate", "roughly": "approximate", "an average of": "average",
    "environ": "approximate", "pres de": "under", "plus de": "over",
    "moins de": "under",
}

_QUALIFIER_RE = re.compile(
    r"(?:" + "|".join(sorted((re.escape(q) for q in _QUALIFIERS), key=len, reverse=True)) + r")\s*$",
    re.I)

#: A word that is part of a number phrase.
_NUMBER_WORD = set(_UNITS) | set(_SCALE) | _HALF | _GLUE

_TOKEN_RE = re.compile(r"[A-Za-zÀ-ſ]+")


def _pre_normalise(text: str) -> str:
    """Fold the compound forms an accumulator cannot see.

    French builds 80 and 90 multiplicatively -- "quatre-vingts" is four twenties
    -- and 70 and 90 additively from 60 and 80. Left to the accumulator,
    "quatre-vingt-dix" would come out as 4 + 20 + 10 = 34. These are rewritten
    to single tokens first.
    """
    t = text
    t = re.sub(r"quatre[\s-]+vingt[s]?[\s-]+dix[\s-]+(?=\w)", "ninety ", t, flags=re.I)
    t = re.sub(r"quatre[\s-]+vingt[s]?[\s-]+dix\b", "ninety", t, flags=re.I)
    t = re.sub(r"quatre[\s-]+vingt[s]?\b", "eighty", t, flags=re.I)
    t = re.sub(r"soixante[\s-]+dix\b", "seventy", t, flags=re.I)
    # Hyphenated English compounds are two number words, not one token.
    t = re.sub(r"(?<=[A-Za-z])-(?=[A-Za-z])", " ", t)
    return t


def words_to_number(phrase: str) -> float | None:
    """The value of a spelled-out number, or None if the phrase is not one.

    >>> words_to_number("three million")
    3000000.0
    >>> words_to_number("forty-two thousand")
    42000.0
    >>> words_to_number("two and a half million")
    2500000.0
    >>> words_to_number("the digesters") is None
    True
    """
    tokens = [w.lower() for w in _TOKEN_RE.findall(_pre_normalise(phrase))]
    if not tokens:
        return None

    total = 0.0        # everything closed off by a scale word
    current = 0.0      # the run being built
    seen_number = False
    pending_half = False
    last_scale = 0.0   # the magnitude a trailing "and a half" belongs to

    for i, word in enumerate(tokens):
        if word in _HALF:
            # A half can arrive before its magnitude or after it, and the two
            # mean the same thing:
            #     "half a million"          0.5 x 1e6   -- waits for the scale
            #     "two and a half million"  2.5 x 1e6   -- waits for the scale
            #     "a million and a half"    1e6 + 0.5e6 -- scale already closed
            #     "un million et demi"      the same, in French
            # The last form is the one that needs `last_scale`: by the time
            # "demi" arrives the million has been banked and `current` is empty,
            # so without this the half becomes a literal 0.5 and the sentence
            # reports 1,000,000.5 gallons.
            if not current and last_scale:
                total += 0.5 * last_scale
            else:
                pending_half = True
            seen_number = True
            continue

        if word in _SCALE:
            scale = _SCALE[word]
            if pending_half:
                # "two and a half million" is 2.5; "half a million" is 0.5, NOT
                # 1.5. The implicit 1 that a bare "a million" gets must not also
                # be granted to a leading half, which already states its own
                # quantity.
                base = current + 0.5 if current else 0.5
                pending_half = False
            else:
                base = current if current else 1.0
            if scale == 100:
                # "three hundred" scales the run; "three hundred thousand" must
                # keep scaling it, so 100 multiplies rather than closing.
                current = base * scale
            else:
                total += base * scale
                current = 0.0
                last_scale = scale
            seen_number = True
            continue

        if word in _UNITS:
            current += _UNITS[word]
            seen_number = True
            continue

        if word in _GLUE:
            continue

        # Anything else ends the number.
        break

    if not seen_number:
        return None
    if pending_half:
        current += 0.5
    value = total + current
    # A phrase of pure glue ("a", "of") parses to nothing.
    return value if (value or _has_zero_word(tokens)) else None


def _has_zero_word(tokens: list[str]) -> bool:
    return any(t in ("zero", "nil", "none") for t in tokens)


@dataclass
class SpelledNumber:
    """A number the page wrote in words, and enough context to judge it."""

    value: float
    phrase: str
    start: int
    end: int
    #: True when the phrase carried "hundred"/"thousand"/"million"/... A phrase
    #: without one is usually an article ("one of the plants"), not a quantity.
    has_magnitude: bool
    #: "over" / "under" / "approximate" / "average", from words like "just over".
    qualifier: str | None
    #: The few words that follow, so a caller can look for a unit.
    trailing: str

    @property
    def looks_like_a_quantity(self) -> bool:
        """Conservative test for callers that must not get looser.

        A magnitude word, or a unit-ish word immediately after, or a value big
        enough that nobody writes it by accident. Bare "one" and "two" fail this
        deliberately.
        """
        if self.has_magnitude:
            return True
        if self.value >= 20:
            return True
        return bool(_UNIT_AFTER_RE.match(self.trailing))


#: Enough of a unit vocabulary to tell "three feet" from "three of them". Not
#: the authority on units -- concordance.units is -- just a gate.
_UNIT_AFTER_RE = re.compile(
    r"\s*(?:gallons?|litres?|liters?|feet|foot|inches|inch|miles?|acres?|yards?|"
    r"tons?|tonnes?|pounds?|lbs?|kilograms?|kg|grams?|degrees?|per\s?cent|percent|"
    r"%|hours?|days?|weeks?|months?|years?|people|persons|residents|inhabitants|"
    r"households?|dwellings?|families|farms?|schools?|beds?|cases?|samples?|"
    r"gallons\s+per|cubic|square|million|thousand|"
    r"gallons?|pieds?|litres?|tonnes?|livres?|personnes|habitants|annees?|jours?)"
    r"\b", re.I)


def scan(text: str) -> list[SpelledNumber]:
    """Every spelled-out number in a sentence, with context.

    Overlapping runs are not returned twice: the longest phrase wins, so
    "three million" yields 3,000,000 and not also 3.
    """
    normalised = _pre_normalise(text)
    found: list[SpelledNumber] = []

    matches = list(_TOKEN_RE.finditer(normalised))
    i = 0
    while i < len(matches):
        if matches[i].group().lower() not in _NUMBER_WORD:
            i += 1
            continue
        # A phrase may not START on glue -- "a" and "of" are only joiners.
        if matches[i].group().lower() in _GLUE and matches[i].group().lower() not in _UNITS:
            i += 1
            continue

        j = i
        last_real = i  # last token that was not pure glue
        while j + 1 < len(matches) and matches[j + 1].group().lower() in _NUMBER_WORD:
            j += 1
            if matches[j].group().lower() not in _GLUE:
                last_real = j

        start, end = matches[i].start(), matches[last_real].end()
        phrase = normalised[start:end]
        value = words_to_number(phrase)
        if value is not None:
            words = {m.group().lower() for m in matches[i:last_real + 1]}
            before = normalised[max(0, start - 24):start]
            q = _QUALIFIER_RE.search(before)
            found.append(SpelledNumber(
                value=value,
                phrase=phrase,
                start=start,
                end=end,
                has_magnitude=bool(words & _MAGNITUDE),
                qualifier=_QUALIFIERS.get(q.group().strip().lower()) if q else None,
                trailing=normalised[end:end + 40],
            ))
        i = j + 1

    return found


def quantities_in(text: str) -> list[SpelledNumber]:
    """Only the spelled-out numbers that are plausibly measurements."""
    return [n for n in scan(text) if n.looks_like_a_quantity]


def states_value(text: str, value: float, *, rel: float = 0.02) -> SpelledNumber | None:
    """Does this sentence state `value` in words?

    Used by verification, so it is deliberately the strict door: only phrases
    that pass `looks_like_a_quantity` count, and the match is within 2% to allow
    a reader to round "just over three million" to 3,000,000 -- which is what a
    correct reader does with that sentence.
    """
    for n in quantities_in(text):
        if n.value == value:
            return n
        scale = max(abs(n.value), abs(value))
        if scale and abs(n.value - value) / scale <= rel:
            return n
    return None
