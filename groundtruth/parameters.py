"""What was measured, resolved to a canonical parameter.

Place names needed resolving across 150 years; so does the *quantity*. A model
reading sixty years of reports writes the same measurement a dozen ways, and
substring matching on those names silently merges things that are not the same:

* "BOD" matches "BOD removal" -- a concentration in mg/L and a percentage.
* "suspended solids" matches "suspended solids removal" -- same trap.
* "flow" matches "daily flow", "total flow" and "average flow" -- a rate, a
  yearly volume, and a rate again.
* "biochemical oxygen demand removal" and "BOD removal" are one measurement
  under two names, and must merge.

All four were found in the Owen Sound series, where the effluent-concentration
chart was silently plotting removal percentages.

A parameter is therefore two things, and a match requires BOTH to agree:

    substance   what was measured        (bod, suspended solids, chlorine, ...)
    measure     what kind of number      (concentration, removal, rate, total)

Getting `substance` right and `measure` wrong is the dangerous case, because the
numbers remain plausible: a removal percentage and a concentration are both
small positive numbers that trend downward when a plant improves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: What kind of quantity a name denotes. Two readings may only join a series when
#: these agree -- a percentage and a concentration are never the same series.
Measure = str  # "concentration" | "removal" | "rate" | "total" | "capacity" | "count" | "other"

#: Substance synonyms found in the corpus. Longest match wins, so "biochemical
#: oxygen demand" resolves before a bare "oxygen" ever could.
_SUBSTANCE: list[tuple[str, str]] = [
    ("biochemical oxygen demand", "bod"),
    ("five day bod", "bod"),
    ("5-day bod", "bod"),
    ("bod5", "bod"),
    ("bod", "bod"),
    ("suspended solids", "suspended solids"),
    ("total solids", "total solids"),
    ("volatile solids", "volatile solids"),
    ("s.s.", "suspended solids"),
    ("ss", "suspended solids"),
    ("chlorine residual", "chlorine residual"),
    ("chlorine dosage", "chlorine"),
    ("chlorine", "chlorine"),
    ("phosphorus", "phosphorus"),
    ("nitrate", "nitrate"),
    ("ammonia", "ammonia"),
    ("coliform", "coliform"),
    ("ph", "ph"),
    ("grit", "grit"),
    ("sludge", "sludge"),
    ("sewage", "sewage"),
    ("population", "population"),
    ("flow", "flow"),
]

#: Word patterns that determine the *measure*. Order matters: "removal" must be
#: tested before "rate", or "BOD removal rate" resolves to a rate.
_MEASURE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(removal|removed|reduction|efficiency)\b"), "removal"),
    (re.compile(r"\b(per capita|per\s+million|per\s+day|daily|per\s+month|monthly|rate)\b"), "rate"),
    (re.compile(r"\b(total|annual|yearly|cumulative)\b"), "total"),
    (re.compile(r"\b(design|capacity|rated)\b"), "capacity"),
    (re.compile(r"\b(count|number|population)\b"), "count"),
]

#: A unit is decisive when the words are ambiguous: whatever a name says, a value
#: in "%" is a removal or fraction, and one in mg/L is a concentration.
_UNIT_MEASURE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^\s*(%|percent|per cent)\s*$", re.I), "removal"),
    (re.compile(r"mg\s*/\s*[l1i]|ppm", re.I), "concentration"),
    (re.compile(r"/\s*(day|d|month|hour|min)\b|mgd|gpm|scfm", re.I), "rate"),
]


@dataclass(frozen=True)
class Parameter:
    substance: str
    measure: Measure
    raw: str

    @property
    def key(self) -> str:
        return f"{self.substance}|{self.measure}"

    @property
    def label(self) -> str:
        if self.measure == "removal":
            return f"{self.substance} removal"
        if self.measure == "total":
            return f"total {self.substance}"
        if self.measure == "rate":
            return f"{self.substance} rate"
        if self.measure == "capacity":
            return f"design {self.substance}"
        return self.substance

    def matches(self, other: "Parameter | None") -> bool:
        return other is not None and self.key == other.key


def resolve(name: str, unit: str | None = None) -> Parameter | None:
    """Canonical parameter for a raw name, using the unit to disambiguate.

    Returns None when the substance is unrecognised. Callers should keep such
    readings rather than discard them -- an unrecognised parameter is a gap in
    this table, not a defect in the record.
    """
    if not name:
        return None
    t = re.sub(r"[^a-z0-9%/. ]+", " ", str(name).lower())
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return None

    substance = None
    for needle, canon in _SUBSTANCE:
        if re.search(rf"(?<![a-z]){re.escape(needle)}(?![a-z])", t):
            substance = canon
            break
    if substance is None:
        return None

    # The unit overrules the wording. "BOD removal" reported in mg/L is a
    # concentration whatever the label claims, and a value in "%" is not.
    measure = None
    if unit:
        for pat, m in _UNIT_MEASURE:
            if pat.search(str(unit)):
                measure = m
                break

    if measure in (None, "concentration", "rate"):
        for pat, m in _MEASURE_PATTERNS:
            if pat.search(t):
                # A unit of % beats any wording; otherwise wording refines it.
                if measure == "removal":
                    break
                measure = m
                break

    if measure is None:
        measure = "concentration" if substance not in {"flow", "population"} else "rate"

    return Parameter(substance=substance, measure=measure, raw=name)


def same_measurement(a: str, a_unit: str | None, b: str, b_unit: str | None) -> bool:
    """Do two raw parameter names denote the same measurement?"""
    pa, pb = resolve(a, a_unit), resolve(b, b_unit)
    if pa is None or pb is None:
        # Fall back to exact string equality rather than guessing. Merging two
        # unrecognised names because they share a word is how the effluent chart
        # ended up plotting removal percentages.
        return a.strip().lower() == b.strip().lower()
    return pa.key == pb.key


#: Facility classes found in this collection. A place commonly has more than one,
#: and they measure opposite things -- a pollution control plant reports what the
#: town discharged, a water supply system reports what residents drank.
_FACILITY_PATTERNS: list[tuple[str, str]] = [
    (r"water pollution control|sewage treatment|sewage works|pollution control plant",
     "water pollution control plant"),
    (r"drinking water surveillance|water supply system|water treatment plant|waterworks",
     "water supply system"),
    (r"landfill|waste disposal", "waste site"),
    (r"air quality|ambient air", "air monitoring"),
]


def facility_of(title: str) -> str | None:
    """Which kind of facility a document reports on.

    Owen Sound has sewage annual reports through 1974 and Drinking Water
    Surveillance reports from 1990 in the same collection, both titled "annual
    report" and both about Owen Sound. Without this they merge, and effluent
    ends up charted against tap water.
    """
    if not title:
        return None
    t = str(title).lower()
    for pattern, name in _FACILITY_PATTERNS:
        if re.search(pattern, t):
            return name
    return None
