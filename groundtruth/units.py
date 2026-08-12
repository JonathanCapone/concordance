"""Units, and knowing when two numbers must not be compared.

This is the methods-drift layer. Its job is as much to REFUSE as to convert,
because the failure mode here is not a crash -- it is a smooth, confident,
entirely fictional trend line drawn through values that were never commensurable.

The problems are real and were found in the corpus, not imagined:

* **Same quantity, different spelling.** The Owen Sound plant's design BOD is
  "180 PPM" in the 1963 report and "180 mg/1" in the 1969 one. Same specification,
  same plant, six years apart.
* **Imperial vs US gallons.** Canadian reports of this era say "million Imperial
  gallons per day". An Imperial gallon is 1.20095 US gallons, so reading one as
  the other overstates or understates every flow by 20%.
* **Scale prefixes.** "3.0 million gallons" and "3000000 gallons" are one value.
* **Genuinely incommensurable pairs.** BOD reported as a concentration (mg/L) and
  BOD reported as a load (lb/day) are different physical quantities. Converting
  between them needs the flow, and guessing is how a plant that improved gets
  charted as a plant that got worse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: Canonical dimension for each base unit. Two values may only be compared when
#: their dimensions match -- this is the check that does the refusing.
DIMENSION: dict[str, str] = {
    "mg/l": "concentration",
    "ppm": "concentration",
    "%": "fraction",
    "gal": "volume",
    "l": "volume",
    "cuft": "volume",
    "gal/day": "flow",
    "l/day": "flow",
    "kg": "mass",
    "lb": "mass",
    "lb/day": "mass_rate",
    "kg/day": "mass_rate",
    "person": "count",
    "min": "time",
    "hour": "time",
    "m": "length",
    "ft": "length",
    "c": "temperature",
    "$": "currency",
}

#: An Imperial gallon is 1.20095 US gallons. Canadian government reports of the
#: 1960s and 70s mean Imperial unless they say otherwise, and treating them as US
#: gallons misstates every flow in the corpus by about 20%.
IMPERIAL_TO_US = 1.20095

_SCALE_WORDS: dict[str, float] = {
    "million": 1e6, "mil": 1e6, "thousand": 1e3, "k": 1e3, "billion": 1e9,
}


@dataclass(frozen=True)
class Quantity:
    """A value reduced to a base unit, with what was assumed to get there."""

    value: float
    unit: str                       # canonical base unit
    dimension: str
    assumptions: tuple[str, ...] = ()

    @property
    def is_safe(self) -> bool:
        """False when an assumption was made that a reader should see."""
        return not self.assumptions


class Incommensurable(ValueError):
    """Raised when two quantities cannot honestly be compared."""


def _clean(text: str) -> str:
    t = str(text).strip().lower()
    t = t.replace("imp.", "imperial").replace("imp ", "imperial ")
    t = re.sub(r"[()]", " ", t)
    return re.sub(r"\s+", " ", t).strip(" .")


#: Units whose meaning depends on what is being measured.
#:
#: "mg" is the worst of them. In Ontario waterworks writing of this era it means
#: MILLION GALLONS -- the 1967 Owen Sound report says "the total flow to the
#: plant in 1967 was 1415.50 mg" and "an average daily flow of 3.88 mg". In every
#: other context it means milligrams. Resolving it needs the parameter, so a
#: bare "mg" with no context is refused rather than guessed.
_AMBIGUOUS: dict[str, dict[str, str]] = {
    # A *rate* ("an average daily flow of 3.88 mg") is million gallons per day.
    # A *total* ("the total flow in 1967 was 1415.50 mg") is a plain volume.
    # Reading the rate as a volume silently drops it out of the flow series.
    "mg": {"rate": "million gallons per day", "total": "million gallons"},
}


def _disambiguate(t: str, parameter: str | None) -> str | None:
    """Resolve a context-dependent unit using the parameter, or give up."""
    options = _AMBIGUOUS.get(t)
    if options is None or not parameter:
        return None
    from .parameters import resolve as resolve_parameter

    p = resolve_parameter(parameter)
    if p is None:
        return None
    if p.substance == "flow":
        return options["total"] if p.measure == "total" else options["rate"]
    return None


def parse_unit(
    raw: str | None, *, era: int | None = None, parameter: str | None = None
) -> Quantity | None:
    """Reduce a unit string to a base unit and a scale multiplier.

    Returns a Quantity with value=multiplier, so callers can apply it. None when
    the unit is not recognised -- deliberately, rather than guessing, because an
    unrecognised unit that gets coerced into a known one is how a corpus quietly
    acquires wrong numbers.
    """
    if not raw:
        return None
    t = _clean(raw)
    assumptions: list[str] = []
    mult = 1.0

    for word, factor in _SCALE_WORDS.items():
        if re.search(rf"\b{word}\b", t):
            mult *= factor
            t = re.sub(rf"\b{word}\b", " ", t).strip()
            break

    imperial = "imperial" in t
    if imperial:
        t = t.replace("imperial", " ").strip()

    t = re.sub(r"\s+", " ", t).strip()

    # Context-dependent units first: "mg" means million gallons in a flow
    # context and milligrams everywhere else, and only the parameter can say.
    resolved = _disambiguate(t, parameter)
    if resolved is not None:
        inner = parse_unit(resolved, era=era)
        if inner is not None:
            return Quantity(
                inner.value * mult, inner.unit, inner.dimension,
                inner.assumptions
                + ('"mg" read as million gallons (Ontario waterworks usage of the era)',),
            )

    # concentration
    if re.fullmatch(r"mg\s*/\s*[l1i]", t) or t in {"mgl", "mg per litre", "mg per liter"}:
        return Quantity(mult, "mg/l", "concentration")
    # Micrograms and nanograms per litre. These are the units drinking-water
    # surveillance reports use for trace contaminants -- trihalomethanes, lead,
    # toluene -- and without them every one of those readings was unusable.
    # Folded to mg/L so a trace reading and a bulk reading of the same substance
    # can sit on one axis; 8 ug/L is 0.008 mg/L, not 8.
    if re.fullmatch(r"(u|µ|mc)g\s*/\s*[l1i]", t) or t in {"ugl", "ug per litre"}:
        return Quantity(mult * 1e-3, "mg/l", "concentration")
    if re.fullmatch(r"ng\s*/\s*[l1i]", t):
        return Quantity(mult * 1e-6, "mg/l", "concentration")
    if t in {"ppm", "p.p.m", "parts per million"}:
        # For dilute aqueous solutions 1 ppm == 1 mg/L. True for sewage effluent,
        # NOT true in general, so the assumption is recorded rather than hidden.
        return Quantity(mult, "mg/l", "concentration",
                        ("ppm treated as mg/L (valid for dilute aqueous samples)",))

    # fraction
    if t in {"%", "percent", "per cent", "pct"}:
        return Quantity(mult, "%", "fraction")

    # flow
    if t in {"mgd", "mg/d"} or re.fullmatch(r"gal(?:lons)?\s*/?\s*(?:per\s*)?day", t):
        base = 1e6 if t in {"mgd", "mg/d"} else 1.0
        if t in {"mgd", "mg/d"}:
            # "MGD" in a Canadian report of this era means Imperial.
            assumptions.append("MGD read as million Imperial gallons/day")
            imperial = True
        v = mult * base
        if imperial:
            v *= IMPERIAL_TO_US
            if "MGD" not in " ".join(assumptions):
                assumptions.append("Imperial gallons converted to US gallons")
        return Quantity(v, "gal/day", "flow", tuple(assumptions))

    # volume
    if re.fullmatch(r"gal(?:lons)?", t):
        v = mult * (IMPERIAL_TO_US if imperial else 1.0)
        if imperial:
            assumptions.append("Imperial gallons converted to US gallons")
        elif era is not None and era < 1980:
            # Canadian reports before metrication almost always meant Imperial,
            # but "almost always" is not "always", so this is flagged not applied.
            assumptions.append(
                f"unqualified 'gallons' in a {era} Canadian report is probably "
                "Imperial; NOT converted"
            )
        return Quantity(v, "gal", "volume", tuple(assumptions))

    if t in {"cu ft", "cuft", "cubic feet", "ft3", "cu. ft"}:
        return Quantity(mult, "cuft", "volume")

    # mass and mass rate
    if re.fullmatch(r"(lb|lbs|pounds?)", t):
        return Quantity(mult, "lb", "mass")
    if re.fullmatch(r"(lb|lbs|pounds?)\s*/?\s*(?:per\s*)?day", t):
        return Quantity(mult, "lb/day", "mass_rate")

    # units found by auditing real extracted records
    if t in {"ph", "ph units", "ph unit"}:
        return Quantity(mult, "ph", "ph")
    if t in {"umho/cm", "umhos/cm", "us/cm", "micromhos/cm", "microsiemens/cm"}:
        return Quantity(mult, "us/cm", "conductivity")
    if t in {"c", "°c", "deg c", "degrees c", "celsius"}:
        return Quantity(mult, "c", "temperature")
    if t in {"tons", "ton", "tonnes", "tonne"}:
        return Quantity(mult, "tonne", "mass")
    if t in {"hp", "horsepower"}:
        return Quantity(mult, "hp", "power")
    if t in {"ntu", "ftu", "jtu"}:
        return Quantity(mult, "ntu", "turbidity")

    # misc
    if t in {"persons", "person", "people", "population"}:
        return Quantity(mult, "person", "count")
    if t in {"min", "mins", "minutes", "minute"}:
        return Quantity(mult, "min", "time")
    if t in {"hr", "hrs", "hour", "hours"}:
        return Quantity(mult, "hour", "time")
    if t in {"ft", "feet", "foot"}:
        return Quantity(mult, "ft", "length")
    if t in {"$", "dollars", "cad"}:
        return Quantity(mult, "$", "currency")

    return None


def to_base(
    value: float, unit: str | None, *, era: int | None = None, parameter: str | None = None
) -> Quantity | None:
    """Convert a measured value into its base unit.

    `parameter` disambiguates units whose meaning depends on what is measured.
    """
    q = parse_unit(unit, era=era, parameter=parameter)
    if q is None:
        return None
    return Quantity(value * q.value, q.unit, q.dimension, q.assumptions)


def comparable(a: Quantity | None, b: Quantity | None) -> tuple[bool, str]:
    """May these two be plotted on the same axis?

    Returns (verdict, reason). The reason is meant to be shown to a reader, not
    logged and forgotten: a refusal that cannot be explained looks like a bug and
    will be worked around.
    """
    if a is None or b is None:
        return False, "one of the units was not recognised"
    if a.dimension != b.dimension:
        return False, (
            f"{a.unit} is a {a.dimension} and {b.unit} is a {b.dimension}; "
            "converting between them needs information the document does not give"
        )
    if a.unit != b.unit:
        return False, f"same dimension but different base units ({a.unit} vs {b.unit})"
    notes = tuple(dict.fromkeys(a.assumptions + b.assumptions))
    if notes:
        return True, "comparable, but note: " + "; ".join(notes)
    return True, "comparable"


def normalize_series(
    points: list[tuple[float, float, str | None, float] | tuple[Any, ...]],
    *,
    parameter: str | None = None,
) -> tuple[list[tuple[Any, ...]], list[str], list[str]]:
    """Reduce (year, value, unit, confidence) points to one base unit.

    Returns (points, assumptions, rejected). Points whose unit disagrees with the
    majority dimension are REJECTED rather than coerced -- silently dropping them
    would hide a methods change, and converting them would invent one.

    An input point may carry a FIFTH element, and if it does that element is
    passed through onto the output point as a fourth. The caller uses it to keep
    hold of the record a number came from.

    This exists because the alternative was re-deriving it. The value changes in
    here -- that is the function's job -- so a caller downstream could no longer
    recognise which record produced which point, and the portal fell back to
    matching on the YEAR alone. On the one town page shipped in the repo, twelve
    of thirteen numbers were captioned with a different record's sentence: a
    flow of 2.1 million gallons shown beside a sentence about $53,549.66, under
    a heading promising every number is linked to its scan. A reader who
    followed the link to check found a page saying something else and concluded
    the project fabricates.

    Carrying the source is the only way the caption cannot drift from the
    number. A lookup that reconstructs the association is a second
    implementation of the choice, and this project has been bitten twice by
    having two implementations of one decision.
    """
    parsed: list[tuple[float, Quantity, float, Any]] = []
    rejected: list[str] = []
    for point in points:
        year, value, unit, conf = point[0], point[1], point[2], point[3]
        payload = point[4] if len(point) > 4 else None
        q = to_base(value, unit, era=int(year), parameter=parameter)
        if q is None:
            rejected.append(f"{int(year)}: unrecognised unit {unit!r}")
            continue
        parsed.append((year, q, conf, payload))

    if not parsed:
        return [], [], rejected

    counts: dict[str, int] = {}
    for _, q, _, _ in parsed:
        counts[q.unit] = counts.get(q.unit, 0) + 1
    majority = max(counts, key=lambda k: counts[k])

    out: list[tuple[Any, ...]] = []
    assumptions: list[str] = []
    for year, q, conf, payload in parsed:
        if q.unit != majority:
            rejected.append(
                f"{int(year)}: {q.unit} ({q.dimension}) is not comparable with "
                f"the series unit {majority}"
            )
            continue
        out.append((year, q.value, conf) if payload is None
                   else (year, q.value, conf, payload))
        for a in q.assumptions:
            if a not in assumptions:
                assumptions.append(a)

    return sorted(out), assumptions, rejected
