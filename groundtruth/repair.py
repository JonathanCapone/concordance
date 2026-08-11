"""Tier 0: repairing what the archive doesn't know about itself.

Measured over all 104,241 items in the collection:

    59,819 (57%)  have no subject tag at all
    33,844 (32%)  have no year
    51 distinct   language values, for what is essentially two languages

None of this is anyone's fault. The collection was assembled over a decade from
many contributing libraries, each with its own cataloguing conventions, and
nobody ever went back over the whole thing. But the effect is that more than half
the collection is undiscoverable by topic, and a third of it cannot be placed in
time -- which makes it invisible to exactly the kind of question this project
wants to ask.

What is repairable here, and what is not, is deliberately measured rather than
assumed:

* **Language** -- fully repairable, deterministically. 51 values collapse to a
  handful of ISO 639-2 codes with no guessing.
* **Year** -- only ~6.7% of missing years can be recovered from the title or
  date field. The rest would need the OCR text, where a first page often carries
  a date. That is a larger job and is not attempted here.
* **Subject** -- needs a model, and is not attempted in this module.

Everything produced here is a *proposal*, not an edit. The output is a diff that
can be reviewed and offered back to Internet Archive Canada. Nothing in this
project writes to anyone else's catalogue.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

# --------------------------------------------------------------------------
# language
# --------------------------------------------------------------------------

#: Every spelling observed in the collection, mapped to ISO 639-2/B.
#: Deliberately explicit rather than clever: a lowercase-and-truncate rule would
#: silently map "fre" and "French" together but also mangle codes it has never
#: seen, and a cataloguing repair that guesses is worse than one that abstains.
_LANGUAGE: dict[str, str] = {
    "eng": "eng", "english": "eng", "en": "eng", "eng.": "eng",
    "fre": "fre", "fra": "fre", "french": "fre", "fr": "fre",
    "français": "fre", "francais": "fre",
    "eng-fre": "mul", "fre-eng": "mul", "eng/fre": "mul", "mul": "mul",
    "multiple": "mul", "bilingual": "mul",
    "und": "und", "unknown": "und", "undetermined": "und",
    "ukrainian": "ukr", "ukr": "ukr",
    "ger": "ger", "german": "ger", "deu": "ger",
    "ita": "ita", "italian": "ita",
    "spa": "spa", "spanish": "spa",
    "chi": "chi", "chinese": "chi", "zho": "chi",
    "iku": "iku", "inuktitut": "iku",
    "cre": "cre", "cree": "cre",
    "oji": "oji", "ojibwa": "oji", "ojibwe": "oji",
    "lat": "lat", "latin": "lat",
    "dut": "dut", "dutch": "dut", "nld": "dut",
    "pol": "pol", "polish": "pol",
    "por": "por", "portuguese": "por",
    "rus": "rus", "russian": "rus",
}


def normalize_language(raw: Any) -> tuple[list[str], list[str]]:
    """Canonical ISO 639-2 codes, plus any value we refused to guess at.

    Returns (codes, unresolved). An unresolved value is reported rather than
    dropped: a code this table has never seen is a fact about the catalogue and
    should be visible, not silently discarded.
    """
    values = raw if isinstance(raw, list) else ([raw] if raw else [])
    codes: list[str] = []
    unresolved: list[str] = []
    for v in values:
        key = re.sub(r"\s+", " ", str(v).strip().lower()).strip(".")
        if not key:
            continue
        mapped = _LANGUAGE.get(key)
        if mapped:
            if mapped not in codes:
                codes.append(mapped)
        else:
            unresolved.append(str(v))
    return codes, unresolved


# --------------------------------------------------------------------------
# year
# --------------------------------------------------------------------------

_YEAR = re.compile(r"\b(1[7-9]\d{2}|20[0-2]\d)\b")

#: Titles like "annual report 1969" name the year the report is ABOUT, which is
#: what we want. Titles like "1979-1980" name a reporting period.
_RANGE = re.compile(r"\b(1[7-9]\d{2}|20[0-2]\d)\s*[-/–]\s*(1[7-9]\d{2}|20[0-2]\d)\b")


@dataclass
class YearGuess:
    year: int | None
    confidence: float
    basis: str
    alternatives: list[int] = field(default_factory=list)


def infer_year(item: dict[str, Any]) -> YearGuess:
    """Recover a publication year from the title or date field.

    Only ~6.7% of year-less items yield to this; the remainder would need the
    OCR text. Confidence is graded so a reviewer can accept the unambiguous ones
    in bulk and look at the rest.
    """
    if item.get("year"):
        return YearGuess(None, 0.0, "already has a year")

    title = str(item.get("title") or "")
    date = str(item.get("date") or "")

    for source, basis in ((date, "date field"), (title, "title")):
        if not source:
            continue

        rng = _RANGE.search(source)
        if rng:
            a, b = int(rng.group(1)), int(rng.group(2))
            # A reporting period "1979-1980" is published at or after its end.
            return YearGuess(max(a, b), 0.55, f"{basis} (range {a}-{b})", [min(a, b)])

        hits = [int(h) for h in _YEAR.findall(source)]
        if not hits:
            continue
        uniq = sorted(set(hits))
        if len(uniq) == 1:
            return YearGuess(uniq[0], 0.9, basis)
        # Several distinct years and no range syntax: the latest is the safest
        # guess, but this is genuinely ambiguous and is scored as such.
        return YearGuess(uniq[-1], 0.4, f"{basis} ({len(uniq)} years present)", uniq[:-1])

    return YearGuess(None, 0.0, "no year found in title or date")


# --------------------------------------------------------------------------
# the proposal
# --------------------------------------------------------------------------

@dataclass
class Proposal:
    identifier: str
    field: str
    current: Any
    proposed: Any
    confidence: float
    basis: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "identifier": self.identifier,
            "field": self.field,
            "current": self.current,
            "proposed": self.proposed,
            "confidence": self.confidence,
            "basis": self.basis,
        }


@dataclass
class RepairReport:
    proposals: list[Proposal] = field(default_factory=list)
    unresolved_languages: Counter = field(default_factory=Counter)
    n_items: int = 0

    def summary(self) -> dict[str, Any]:
        by_field = Counter(p.field for p in self.proposals)
        high = sum(1 for p in self.proposals if p.confidence >= 0.85)
        return {
            "items_examined": self.n_items,
            "proposals": len(self.proposals),
            "by_field": dict(by_field),
            "high_confidence": high,
            "unresolved_language_values": dict(self.unresolved_languages),
        }


def repair(items: Iterable[dict[str, Any]], *, min_confidence: float = 0.4) -> RepairReport:
    """Propose metadata corrections. Never mutates the input."""
    report = RepairReport()

    for item in items:
        report.n_items += 1
        ident = item.get("identifier", "")

        raw_lang = item.get("language")
        codes, unresolved = normalize_language(raw_lang)
        for u in unresolved:
            report.unresolved_languages[u] += 1
        if codes:
            existing = raw_lang if isinstance(raw_lang, list) else [raw_lang]
            existing = [str(x) for x in existing if x]
            if existing != codes:
                report.proposals.append(
                    Proposal(
                        identifier=ident,
                        field="language",
                        current=raw_lang,
                        proposed=codes if len(codes) > 1 else codes[0],
                        confidence=1.0,
                        basis="deterministic mapping to ISO 639-2",
                    )
                )

        guess = infer_year(item)
        if guess.year and guess.confidence >= min_confidence:
            report.proposals.append(
                Proposal(
                    identifier=ident,
                    field="year",
                    current=None,
                    proposed=guess.year,
                    confidence=guess.confidence,
                    basis=guess.basis,
                )
            )

    return report
