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

# --------------------------------------------------------------------------
# the vocabulary
# --------------------------------------------------------------------------
#
# Organised by domain so a contributor can add a block for a subject we have
# never read without touching the resolver. This is the part that has to be
# built centrally: whether a number is a measurement, and what of, is a
# judgement about meaning. Running the extractor is just time and electricity,
# and can happen on anyone's machine, in any order, whenever they care enough
# about a subject to spend an hour on it.
#
# A parameter that is not in here is not lost -- it is extracted, flagged as
# unresolved by the audit, and simply cannot join a series until someone names
# it. That is how the water vocabulary grew: an audit found 36.7% of records
# carried a parameter the table had never seen.
#
# Domain terms below are taken from the collection's own subject headings, not
# invented: "Thirteenth grade (Education)", "Forest management -- Ontario",
# "Census districts", "Acid precipitation (Meteorology)".

VOCABULARY: dict[str, list[tuple[str, str]]] = {
    "air": [
        ("sulphur dioxide", "sulphur dioxide"),
        ("sulfur dioxide", "sulphur dioxide"),
        ("so2", "sulphur dioxide"),
        ("nitrogen dioxide", "nitrogen dioxide"),
        ("no2", "nitrogen dioxide"),
        ("carbon monoxide", "carbon monoxide"),
        ("ozone", "ozone"),
        ("particulate", "particulate"),
        ("suspended particulate", "particulate"),
        ("dustfall", "dustfall"),
        ("smoke", "smoke"),
        ("acid precipitation", "acid precipitation"),
        ("acid rain", "acid precipitation"),
        ("emission", "emission"),
        ("visibility", "visibility"),
    ],
    "education": [
        ("enrolment", "enrolment"),
        ("enrollment", "enrolment"),
        ("attendance", "attendance"),
        ("examination", "examination result"),
        ("exam", "examination result"),
        ("pass rate", "pass rate"),
        ("failure rate", "failure rate"),
        ("mark", "examination result"),
        ("grade", "examination result"),
        ("score", "examination result"),
        ("candidates", "candidates"),
        ("pupils", "pupils"),
        ("students", "pupils"),
        ("teachers", "teachers"),
        ("classroom", "classrooms"),
        ("expenditure per pupil", "expenditure per pupil"),
    ],
    "agriculture": [
        ("yield", "yield"),
        ("acreage", "acreage"),
        ("area sown", "acreage"),
        ("area harvested", "acreage"),
        ("production", "production"),
        ("livestock", "livestock"),
        ("cattle", "cattle"),
        ("swine", "swine"),
        ("poultry", "poultry"),
        ("fertilizer", "fertiliser"),
        ("fertiliser", "fertiliser"),
        ("pesticide", "pesticide"),
        ("farms", "farms"),
    ],
    "forestry": [
        ("timber", "timber volume"),
        ("cut", "timber cut"),
        ("merchantable volume", "timber volume"),
        ("regeneration", "regeneration"),
        ("basal area", "basal area"),
        ("stocking", "stocking"),
        ("burned area", "burned area"),
        ("forest area", "forest area"),
    ],
    "population": [
        ("dwellings", "dwellings"),
        ("households", "households"),
        ("families", "families"),
        ("density", "population density"),
        ("births", "births"),
        ("deaths", "deaths"),
        ("migration", "migration"),
    ],
    "energy": [
        ("natural gas", "natural gas"),
        ("petroleum", "petroleum"),
        ("crude oil", "crude oil"),
        ("coal", "coal"),
        ("reserves", "reserves"),
        ("consumption", "consumption"),
        ("generation", "generation"),
        ("pipeline throughput", "pipeline throughput"),
    ],
    "mining": [
        ("ore", "ore"),
        ("tonnage", "tonnage"),
        ("grade", "ore grade"),
        ("tailings", "tailings"),
        ("overburden", "overburden"),
    ],
}


def _domain_terms() -> list[tuple[str, str]]:
    """Flatten the domain blocks, longest term first so specific beats general."""
    terms = [pair for block in VOCABULARY.values() for pair in block]
    return sorted(terms, key=lambda p: -len(p[0]))


#: Substance synonyms found in the corpus. Longest match wins, so "biochemical
#: oxygen demand" resolves before a bare "oxygen" ever could.
#:
#: Water terms are listed explicitly here because they were built first and
#: carry the most nuance; the other domains are appended from VOCABULARY.
_WATER_TERMS: list[tuple[str, str]] = [
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

    # Added after auditing 281 extracted records and finding that 36.7% carried
    # a parameter this table had never seen. Those readings were extracted
    # correctly and then dropped from every series in silence, which is the
    # failure this project keeps having to catch: the table was the gap, not the
    # extraction.
    ("hardness", "hardness"),
    ("conductivity", "conductivity"),
    ("temperature", "temperature"),
    ("turbidity", "turbidity"),
    ("fluoride", "fluoride"),
    ("chloride", "chloride"),
    ("sulphate", "sulphate"),
    ("sulfate", "sulphate"),
    ("iron", "iron"),
    ("manganese", "manganese"),
    ("sodium", "sodium"),
    ("lead", "lead"),
    ("copper", "copper"),
    ("zinc", "zinc"),
    ("aluminum", "aluminium"),
    ("aluminium", "aluminium"),
    # Trihalomethanes: disinfection by-products, and the reason drinking-water
    # surveillance reports exist at all.
    ("trihalomethane", "trihalomethanes"),
    ("thms", "trihalomethanes"),
    ("thm", "trihalomethanes"),
    ("toluene", "toluene"),
    ("benzene", "benzene"),
    ("moisture content", "moisture"),
    ("volatile matter", "volatile matter"),
    # Named specifically. A bare "gas" -- or even "gas production" -- is a
    # sewage term only inside a sewage document, and this table has no idea what
    # document it is in. Left greedy, "natural gas production" resolved to
    # digester gas: a treatment by-product standing in for a fossil fuel.
    ("digester gas", "digester gas"),
    ("sludge gas", "digester gas"),
    ("retention time", "retention time"),
    ("retention", "retention time"),
    ("detention", "retention time"),
    ("operating cost", "cost"),
    ("treatment cost", "cost"),
    ("cost", "cost"),
    ("man hours", "labour"),
    ("plant capacity", "capacity"),
    ("capacity", "capacity"),
    ("diameter", "dimension"),
    ("width", "dimension"),
    ("depth", "dimension"),
    ("volume reduction", "volume reduction"),
]


#: Substances that are counted rather than measured in a concentration. Without
#: this an enrolment of 4,200 pupils resolves as a concentration and lands on an
#: axis with milligrams per litre.
_COUNTED = {
    "population", "pupils", "teachers", "candidates", "classrooms", "enrolment",
    "attendance", "dwellings", "households", "families", "births", "deaths",
    "farms", "cattle", "swine", "poultry", "livestock",
}


def _ordered_vocabulary() -> list[tuple[str, str]]:
    """Every term, longest first.

    Sorting matters across the WHOLE table, not just within a block. The water
    list carries a bare "gas" for digester gas, and with the domain terms merely
    appended, "natural gas production" matched "gas" and resolved to digester
    gas -- a sewage by-product standing in for a fossil fuel.
    """
    return sorted(_WATER_TERMS + _domain_terms(), key=lambda pair: -len(pair[0]))


_SUBSTANCE = _ordered_vocabulary()


def rebuild() -> None:
    """Re-derive the match order after VOCABULARY has been edited at runtime.

    `_SUBSTANCE` is a snapshot taken at import, so adding a term to VOCABULARY
    changes the table and not the answer. Appending ("cordwood", "cordwood")
    and asking for "cordwood cut" still returns `timber cut` until this runs.

    It matters because the vocabulary is meant to be built in rounds: sample,
    harvest what did not resolve, accept the good proposals, measure how much
    that improved things, sample again. Without a rebuild, every round after the
    first scores against the round-one table and reports that nothing improved
    -- so the run would stop early, on evidence that was an artefact of module
    import order, and conclude the vocabulary was finished.
    """
    global _SUBSTANCE
    _SUBSTANCE = _ordered_vocabulary()

#: Wording that means the number counts OCCASIONS rather than quantity.
#: Checked before anything else in resolve(), because an exceedance count and a
#: removal efficiency are both percentages and the unit cannot separate them.
_FREQUENCY = re.compile(
    r"exceedance|exceeded|exceeding|frequency|occasions|of the time|"
    # "objectives met" and "compliance" count OCCASIONS a limit was satisfied,
    # which is the same kind of number as an exceedance and the opposite kind
    # from a removal efficiency. Brantford's 1962 "the objective for BOD was
    # exceeded only 20 per cent of the time" reached the chart as BOD removal
    # 20% -- an excellent year drawn as a failing plant. "exceeded" was already
    # here; "exceeding" and "objectives met" were the spellings that slipped
    # past it.
    r"objectives?\s+(?:met|achieved|satisfied)|compliance|complied",
    re.I,
)

_MEASURE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(removal|removed|reduction|efficiency)\b"), "removal"),
    (re.compile(r"\b(per capita|per\s+million|per\s+day|daily|per\s+month|monthly|rate)\b"), "rate"),
    (re.compile(r"\b(total|annual|yearly|cumulative)\b"), "total"),
    (re.compile(r"\b(design|capacity|rated)\b"), "capacity"),
    (re.compile(r"\b(count|number|population)\b"), "count"),
]

#: A unit is decisive when the words are ambiguous: whatever a name says, a value
#: in "%" is a removal or fraction, and one in mg/L is a concentration.
#: Wording that states a rate even when the unit does not. Kept apart from
#: _MEASURE_PATTERNS because it answers a narrower question: may a bare volume
#: be read as a total here.
_RATE_WORDING = re.compile(
    r"(?<![a-z])(daily|per day|hourly|per hour|monthly|per month|"
    r"per capita|per minute)(?![a-z])", re.I)


_UNIT_MEASURE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^\s*(%|percent|per cent)\s*$", re.I), "removal"),
    (re.compile(r"mg\s*/\s*[l1i]|ppm", re.I), "concentration"),
    (re.compile(r"/\s*(day|d|month|hour|min)(?![a-z])|mgd|gpm|scfm", re.I), "rate"),
    # A bulk mass or volume is a TOTAL, whatever the wording says. "A total of
    # 2,398.4 tons of BOD was removed in 1966" and "BOD removal efficiency was
    # 94%" both say "removal", and they are a mass and a ratio -- so they shared
    # an identity and the chart drew whichever group was larger. Three tonnages
    # outnumbered three percentages, and Brantford's BOD removal series was
    # published in tonnes.
    (re.compile(r"^\s*(?:\d[\d,.]*\s*)?"
                r"(tons?|tonnes?|lbs?|pounds?|kg|kilograms?|grams?|"
                r"gallons?|million gallons|litres?|liters?|"
                r"cubic (?:feet|foot|metres?|meters?)|cu\.? ?ft\.?)"
                r"\s*$", re.I), "total"),
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
        if self.measure == "frequency":
            return f"{self.substance} exceedance frequency"
        if self.measure == "total":
            return f"total {self.substance}"
        if self.measure == "rate":
            return f"{self.substance} rate"
        if self.measure == "capacity":
            return f"design {self.substance}"
        return self.substance

    def matches(self, other: "Parameter | None") -> bool:
        return other is not None and self.key == other.key


#: Everything from a ratio's "per" onward. Written with a lookahead rather
#: than a word-boundary escape: this project has lost hours three times to a
#: `\b` becoming a literal backspace byte in a shell heredoc.
#: ...but only where "per" introduces a QUANTITY, which is what makes the rest
#: of the name a denominator. "per lb BOD removed" and "per pound volatile
#: matter" normalise by a mass and the substance is whatever came before them.
#: "per capita", "per month", "per cent" and "per day" are qualifiers -- they
#: say what kind of number it is, not what it is of -- and stripping those lost
#: "Daily Per Capita Flow" entirely, since there the qualifier sits in front of
#: the substance rather than after it.
_RATIO_DENOMINATOR = re.compile(
    r"(?<![a-z])per\s+"
    r"(?:\d[\d,.]*\s+)?"
    r"(?:lb|lbs|pound|pounds|ton|tons|tonne|tonnes|kg|kilogram|kilograms|"
    r"gram|grams|gallon|gallons|million\s+gallons|litre|litres|liter|liters|"
    r"cubic\s+\w+|acre|acres|hectare|hectares|foot|feet|square\s+\w+)"
    r"(?![a-z]).*$", re.I)


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

    # "X per Y" measures X, not Y. Without this, "CUBIC FEET AIR PER LB BOD
    # REMOVED" resolved to bod/removal on the strength of the word BOD, and
    # Brantford's BOD-removal chart plotted an air-supply ratio: twelve monthly
    # readings around 1,200 cubic feet, outnumbering the two real removal
    # percentages, so the majority rule then labelled the axis in cubic feet and
    # the series was wrong rather than merely mislabelled.
    #
    # This is the same greedy-substring failure that once made "natural gas
    # production" resolve to digester gas. The denominator of a ratio is the
    # thing being normalised BY, and it is never what the number measures.
    #
    # The denominator is stripped for the SUBSTANCE only. The measure still
    # reads the whole name, because "per month" and "per capita" say what KIND
    # of number this is even when they say nothing about what it is of --
    # stripping them everywhere turned "chlorine used per month" from a rate
    # into a concentration and lost "Daily Per Capita Flow" entirely.
    head = _RATIO_DENOMINATOR.sub("", t).strip() or t

    substance = None
    for needle, canon in _SUBSTANCE:
        if re.search(rf"(?<![a-z]){re.escape(needle)}(?![a-z])", head):
            substance = canon
            break
    if substance is None:
        return None

    # Frequency is decided by wording alone, and decided FIRST.
    #
    # An exceedance count and a removal efficiency are both percentages, so the
    # unit cannot separate them and whichever is tested first wins everything.
    # The Brantford 1962 report says "the Commission's objective for BOD was
    # exceeded only 20 per cent of the time", which the extractor filed as "BOD
    # removal 20%". That inverts the meaning: 20% exceedance is a good year,
    # 20% removal is a failing plant.
    if _FREQUENCY.search(t):
        return Parameter(substance=substance, measure="frequency", raw=name)

    # Otherwise the unit overrules the wording. "BOD removal" reported in mg/L is
    # a concentration whatever the label claims, and a value in "%" is not.
    #
    # With one exception, which the flow series taught: a BARE mass or volume
    # means a total only when the name does not already say otherwise. "Daily
    # flow: 6.12 million gallons" carries its rate in the wording and not in the
    # unit, and letting the unit win moved a day's flow into the annual series.
    # A "/day" in the unit still decides, because that is the unit disagreeing
    # rather than merely being silent.
    says_rate = bool(_RATE_WORDING.search(t))
    measure = None
    if unit:
        for pat, m in _UNIT_MEASURE:
            if pat.search(str(unit)):
                if m == "total" and says_rate:
                    continue
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
        if substance in _COUNTED:
            measure = "count"
        elif substance in {"flow"}:
            measure = "rate"
        else:
            measure = "concentration"

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
