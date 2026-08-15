"""Archive-native tools: the things an agent needs to be useful over this data.

Written as plain functions with JSON-shaped returns so they can be mounted into
an agent's tool registry, exposed over HTTP, or called from a script, without
this module knowing which. It deliberately imports nothing beyond the standard
library, so the tool layer stays runnable by anyone who clones the repo.

The design bias throughout: a person who is not a scientist must be able to get a
straight answer, and must be able to check it. Every tool that returns a number
returns the scanned page it came from alongside it.
"""

from __future__ import annotations

import collections
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import Provenance, Record
from .parameters import resolve as resolve_parameter
from .places import attach_subunits, scope_record_dict
from .science import series_from_records, silence, trend

# --------------------------------------------------------------------------
# what these numbers mean, in plain language
# --------------------------------------------------------------------------

#: Enough context to answer "is that bad?" without a chemistry degree.
#:
#: `typical_modern` figures are indicative of contemporary Ontario municipal
#: practice and are here to give a reader a sense of scale. They are NOT the
#: regulatory standard of the era being read -- judging a 1969 measurement
#: against a modern guideline is a category error that produces a damning and
#: meaningless result. Where the archive itself yields a contemporary standard,
#: that is extracted as a `standard` record and should be preferred.
GLOSSARY: dict[str, dict[str, Any]] = {
    "bod": {
        "name": "BOD (biochemical oxygen demand)",
        "plain": (
            "How much oxygen the waste will consume as it rots. High BOD in a river "
            "starves fish of oxygen, so it is the single most-watched number in sewage "
            "treatment."
        ),
        "units": "mg/L",
        "typical_modern": 25.0,
        "modern_note": "modern Ontario effluent is commonly held near 25 mg/L or lower",
        "modern_phrase": "the modern 25 mg/L benchmark",
        "direction": "lower is better",
    },
    "suspended solids": {
        "name": "suspended solids",
        "plain": (
            "The solid matter still floating in the water. It clouds the river, smothers "
            "riverbed habitat, and carries other pollutants with it."
        ),
        "units": "mg/L",
        "typical_modern": 25.0,
        "modern_note": "modern Ontario effluent is commonly held near 25 mg/L or lower",
        "modern_phrase": "the modern 25 mg/L benchmark",
        "direction": "lower is better",
    },
    "phosphorus": {
        "name": "phosphorus",
        "plain": (
            "A nutrient. Too much of it makes algae bloom, which then rots and removes "
            "the oxygen -- the main cause of the Great Lakes algae problems of the era."
        ),
        "units": "mg/L",
        "typical_modern": 1.0,
        "modern_note": "commonly limited near 1 mg/L",
        "modern_phrase": "the modern 1 mg/L benchmark",
        "direction": "lower is better",
    },
    "chlorine residual": {
        "name": "chlorine residual",
        "plain": (
            "Chlorine still left in the water after disinfection. Some is needed to kill "
            "bacteria; too much is itself toxic to river life."
        ),
        "units": "mg/L",
        "typical_modern": 0.5,
        "modern_note": "often kept below ~0.5 mg/L where discharged to a river",
        "modern_phrase": "the modern 0.5 mg/L benchmark",
        "direction": "a balance, not a minimum",
    },
    "flow": {
        "name": "flow",
        "plain": "How much sewage passed through the plant.",
        "units": "gal/day",
        "typical_modern": None,
        "modern_note": "compare against the plant's design capacity, not a fixed number",
        "direction": "context, not quality",
    },
}


def explain_this_number(
    parameter: str,
    value: float | None = None,
    unit: str | None = None,
    year: int | None = None,
    *,
    era_standard: float | None = None,
) -> dict[str, Any]:
    """Plain-language explanation of a measurement, for a non-specialist.

    If a contemporary standard is supplied it is used for the verdict. Otherwise
    the answer says explicitly that it is comparing against modern practice, so
    nobody mistakes "worse than today" for "illegal at the time".
    """
    p = resolve_parameter(parameter, unit)
    key = p.substance if p else str(parameter).lower()
    g = GLOSSARY.get(key)

    out: dict[str, Any] = {
        "parameter": parameter,
        "resolved": p.key if p else None,
        "value": value,
        "unit": unit,
        "year": year,
    }
    if not g:
        out["explanation"] = (
            f"No plain-language entry for {parameter!r} yet. The measurement is "
            "recorded as-is; it has not been interpreted."
        )
        return out

    out["name"] = g["name"]
    out["explanation"] = g["plain"]
    out["direction"] = g["direction"]

    if value is None:
        return out

    if p and p.measure == "removal":
        out["verdict"] = (
            f"{value:g}% of the {g['name']} was removed before discharge. "
            "Primary treatment of this era typically removed 30-40%; a modern plant "
            "with secondary treatment removes upward of 85%."
        )
        return out

    if era_standard is not None:
        over = value > era_standard
        out["compared_against"] = f"the standard in force at the time ({era_standard:g} {g['units']})"
        out["verdict"] = (
            f"{value:g} {g['units']} is {'above' if over else 'within'} the "
            f"{era_standard:g} {g['units']} limit that applied then."
        )
        return out

    modern = g.get("typical_modern")
    if modern:
        ratio = value / modern
        out["compared_against"] = f"modern practice ({g['modern_note']})"
        out["caveat"] = (
            "This compares a historical measurement against a MODERN benchmark. It "
            "does not mean the plant broke the rules of its own time -- those rules "
            "were different, and often did not exist."
        )
        phrase = g.get("modern_phrase", "modern practice")
        out["verdict"] = (
            f"{value:g} {g['units']} is about {ratio:.1f} times {phrase} "
            f"({g['modern_note']})."
            if ratio >= 1
            else f"{value:g} {g['units']} is below {phrase} ({g['modern_note']})."
        )
    return out


# --------------------------------------------------------------------------
# the record store these tools read
# --------------------------------------------------------------------------

@dataclass
class Corpus:
    """Extracted records for one or more places, loaded from disk."""

    records: list[Record]
    places: list[str]

    @classmethod
    def load(cls, *paths: str | Path) -> "Corpus":
        records: list[Record] = []
        places: list[str] = []
        for path in paths:
            p = Path(path)
            if not p.exists():
                continue
            payload = json.loads(p.read_text(encoding="utf-8"))
            place = payload.get("place")
            if place and place not in places:
                places.append(place)
            for source_record in attach_subunits(list(payload.get("records", []))):
                d = scope_record_dict(source_record, place)
                prov = d.get("provenance") or {}
                period = d.get("period")
                raw = dict(d.get("raw") or {})
                records.append(
                    Record(
                        kind=d["kind"], parameter=d.get("parameter", ""),
                        value=d.get("value"), unit=d.get("unit"),
                        qualifier=d.get("qualifier"), stream=d.get("stream", "unknown"),
                        place=d.get("place"), period=period,
                        # Without this every record loads as "unclassified" and
                        # the facility split silently does nothing -- which is how
                        # Jay came to report that Owen Sound's sewage record runs
                        # to 1992, when that is a drinking-water report that merely
                        # shares the town's name.
                        facility=d.get("facility"),
                        # Dropping this here while record_key includes it would
                        # give the same reading two identities, one on either
                        # side of the loader -- the exact asymmetry that once
                        # re-imported the library's own data as 88 new records.
                        condition=d.get("condition"),
                        confidence=d.get("confidence", 0.0),
                        provenance=Provenance(
                            identifier=prov.get("identifier", ""),
                            page=prov.get("page"),
                            source_text=prov.get("source_text", ""),
                        ),
                        raw=raw,
                    )
                )
        return cls(records=records, places=places)

    @classmethod
    def load_dir(cls, directory: str | Path = "data/results") -> "Corpus":
        d = Path(directory)
        # Identify extraction files by their SHAPE, not by their name failing to
        # appear on a list of known reports.
        #
        # The list matched exact stems, so "gold_report" was excluded and
        # "gold_report.before-prompt-widening" was not -- and a superseded
        # accuracy benchmark contributed 53 records of a previous extractor's
        # output to the published dataset. The same hole was open for every
        # future report anybody drops in this directory, which is the defining
        # weakness of a blocklist: it protects against the files you thought of.
        #
        # A per-place extraction carries a `place` key. Reports do not. The key
        # is tested for PRESENCE, not truth, because a merged contribution
        # writes place="" deliberately -- its records carry their own places and
        # a bundle has no single town.
        out = []
        for path in sorted(d.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            # Presence of `place`, and nothing else. Not its truth -- a merged
            # contribution writes place="" because a bundle has no single town.
            # Not a non-empty `records` either: a town that was read and yielded
            # nothing is a fact worth keeping, and the frontier depends on
            # knowing it has been looked at.
            if isinstance(payload, dict) and "place" in payload:
                out.append(path)
        return cls.load(*out)


# --------------------------------------------------------------------------
# the tools
# --------------------------------------------------------------------------

def standard_for(
    corpus: Corpus,
    parameter: str,
    year: int,
    *,
    max_years_away: int = 15,
) -> dict[str, Any] | None:
    """The regulatory limit in force nearest a given year, from the archive itself.

    Closes the loop that `explain_this_number` leaves open. Without this it
    always falls back to a modern benchmark and has to say so; with it, a 1969
    reading can be judged against a 1969 rule.

    Prefers a standard published at or BEFORE the observation. A limit introduced
    in 1978 tells you nothing about whether a 1969 discharge was acceptable, and
    using it would manufacture retrospective violations -- which is exactly the
    kind of confident, damning, meaningless output this project is trying not to
    produce. A later standard is used only when no earlier one exists, and the
    result says so.
    """
    want = resolve_parameter(parameter)
    candidates: list[tuple[tuple[int, int], Record]] = []

    for r in corpus.records:
        if r.kind != "standard" or r.value is None or not r.period:
            continue
        got = resolve_parameter(r.parameter, r.unit)
        if want is not None:
            if got is None or got.key != want.key:
                continue
        elif parameter.lower() not in r.parameter.lower():
            continue
        try:
            std_year = int(str(r.period)[:4])
        except ValueError:
            continue
        gap = year - std_year
        if abs(gap) > max_years_away:
            continue
        # Rank: earlier-or-equal beats later, then nearest in time.
        candidates.append(((0 if gap >= 0 else 1, abs(gap)), r))

    if not candidates:
        return None

    candidates.sort(key=lambda c: c[0])
    best_rank = candidates[0][0]

    # Many standards are RANGES, not single limits, and the archive states them
    # as such: "the ODWO Aesthetic or Recommended Operational Guideline of
    # 6.5-8.5 pH units". Both bounds come back as separate records for the same
    # parameter and year, and picking whichever sorted first would turn "pH must
    # be between 6.5 and 8.5" into "the limit is 6.5" -- which then reports every
    # normal reading as an exceedance.
    same = [r for rank, r in candidates if rank == best_rank]
    values = sorted({r.value for r in same if r.value is not None})
    rec = same[0]
    std_year = int(str(rec.period)[:4])

    out: dict[str, Any] = {
        "value": values[0] if len(values) == 1 else None,
        "range": [values[0], values[-1]] if len(values) > 1 else None,
        "unit": rec.unit,
        "year": std_year,
        "applies_before_observation": std_year <= year,
        "source": rec.provenance.page_url if rec.provenance else None,
        "read_from": [r.provenance.source_text for r in same if r.provenance][:3],
        "caveat": None if std_year <= year else (
            f"This limit dates from {std_year}, AFTER the {year} reading. It cannot "
            "say whether the discharge was acceptable at the time."
        ),
    }
    if len(values) > 2:
        # Three or more distinct values for one parameter-year is not a range --
        # the archive is stating several different guidelines (desirable,
        # acceptable, "considered poor"), and collapsing them to min and max
        # would invent a limit nobody wrote.
        out["range"] = None
        out["value"] = None
        out["ambiguous_values"] = values
        out["caveat"] = (
            f"The archive states {len(values)} different guideline values for this "
            f"parameter in {std_year} ({', '.join(str(v) for v in values)}). They are "
            "probably different classes of guideline -- desirable, acceptable, poor -- "
            "and no single limit can be inferred from them."
        )
    return out


def judge_reading(
    corpus: Corpus, parameter: str, value: float, unit: str | None, year: int
) -> dict[str, Any]:
    """Explain a measurement, using the era's own standard where the archive has one."""
    std = standard_for(corpus, parameter, year)
    # Only a single, unambiguous, contemporary limit can produce a verdict. A
    # range or a set of competing guidelines is reported to the reader rather
    # than collapsed into one number to judge against.
    usable = (
        std["value"]
        if std and std["applies_before_observation"] and std.get("value") is not None
        else None
    )
    out = explain_this_number(parameter, value, unit, year, era_standard=usable)
    if std:
        out["standard"] = std
        if std.get("range") and value is not None:
            lo, hi = std["range"]
            inside = lo <= value <= hi
            out["verdict"] = (
                f"{value:g} {unit or ''} is {'within' if inside else 'outside'} the "
                f"{lo:g}-{hi:g} range that applied in {std['year']}.".replace("  ", " ")
            )
            out.pop("caveat", None)
    return out


def find_my_town(corpus: Corpus, place: str, facility: str | None = None) -> dict[str, Any]:
    """Everything ever measured about a place, summarised.

    Reports ONE facility at a time. A town commonly has several and they measure
    opposite things -- a pollution control plant reports what was discharged, a
    water supply system reports what residents drank. Merged, the summary claims
    a town's sewage record runs to 1992 when it actually ends in 1972 and a
    drinking-water report happens to share the town's name.
    """
    want = place.strip().lower()
    mine = [r for r in corpus.records if (r.place or "").strip().lower() == want]
    if not mine:
        return {
            "place": place,
            "found": False,
            "message": f"No records for {place!r}. Known places: "
                       + ", ".join(sorted(corpus.places)),
        }

    present = collections.Counter(r.facility or "unclassified" for r in mine)
    chosen = facility or present.most_common(1)[0][0]
    mine = [r for r in mine if (r.facility or "unclassified") == chosen]

    years = sorted({int(str(r.period)[:4]) for r in mine
                    if r.period and str(r.period)[:4].isdigit()})
    obs = [r for r in mine if r.kind == "observation"]
    params: dict[str, int] = {}
    for r in obs:
        p = resolve_parameter(r.parameter, r.unit)
        k = p.label if p else r.parameter
        params[k] = params.get(k, 0) + 1

    return {
        "place": place,
        "found": True,
        "facility": chosen,
        "other_facilities": [f for f in present if f != chosen],
        "years": years,
        "span": [years[0], years[-1]] if years else None,
        "n_records": len(mine),
        "n_measurements": len(obs),
        "measured": sorted(params.items(), key=lambda kv: -kv[1]),
        "sources": sorted({r.provenance.identifier for r in mine if r.provenance}),
    }


def show_the_page(corpus: Corpus, record_key: str) -> dict[str, Any]:
    """Resolve any recorded number back to the scan it was read from.

    This is the tool that makes every other one falsifiable.
    """
    for r in corpus.records:
        if r.key == record_key and r.provenance:
            return {
                "found": True,
                "value": r.value,
                "unit": r.unit,
                "parameter": r.parameter,
                "period": r.period,
                "place": r.place,
                "read_from": r.provenance.source_text,
                "page_url": r.provenance.page_url,
                "item_url": r.provenance.item_url,
                "page": r.provenance.page,
                "reading_confidence": r.confidence,
            }
    return {"found": False, "message": f"no record with key {record_key!r}"}


def what_went_quiet(
    silence_report: str | Path = "data/results/silence_report.json",
    *,
    year: int | None = None,
) -> dict[str, Any]:
    """Which places stopped being measured, and whether that is real.

    Always returns the digitisation control alongside the finding, because the
    finding is not interpretable without it.
    """
    p = Path(silence_report)
    if not p.exists():
        return {"available": False, "message": "run scripts/silence_report.py first"}
    data = json.loads(p.read_text(encoding="utf-8"))

    munis = data["municipalities"]
    if year is not None:
        munis = [m for m in munis if m.get("silent_since") == year]

    return {
        "available": True,
        "n_municipalities": len(munis),
        "largest_simultaneous_stop": data["largest_simultaneous_stop"],
        "control": data["digitisation_control"],
        "control_verdict": data["control_verdict"],
        "caveat": data["caveat"],
        "places": [
            {"place": m["place"], "last_year": m["last_year"],
             "silent_since": m.get("silent_since")}
            for m in sorted(munis, key=lambda m: m["place"])
        ],
    }


def read_me_the_record(corpus: Corpus, place: str) -> dict[str, Any]:
    """A place's story, assembled across decades, in order, with sources.

    Not a query result -- a narrative. Every claim carries the sentence it came
    from so the story can be checked line by line.
    """
    summary = find_my_town(corpus, place)
    if not summary.get("found"):
        return summary

    want = place.strip().lower()
    obs = [r for r in corpus.records
           if (r.place or "").strip().lower() == want and r.kind == "observation"]

    chapters: list[dict[str, Any]] = []
    for param_name in ("BOD removal", "suspended solids removal", "daily flow"):
        s = series_from_records(obs, parameter=param_name)
        if len(s) < 2:
            continue
        t = trend(s.points)
        first_y, first_v, _ = s.points[0]
        last_y, last_v, _ = s.points[-1]
        chapters.append({
            "parameter": param_name,
            "unit": s.unit,
            "from": {"year": int(first_y), "value": first_v},
            "to": {"year": int(last_y), "value": last_v},
            "change": last_v - first_v,
            "trend": t.describe(),
            "assumptions": s.assumptions,
            "rejected": s.rejected,
        })

    years = summary.get("years") or []
    quiet = silence(place, years, horizon=1996) if years else None

    return {
        "place": place,
        "opening": (
            f"{place} filed {len(summary['sources'])} reports to the Ontario "
            f"government between {years[0]} and {years[-1]}."
            if years else f"{place} has records but none are dated."
        ),
        "chapters": chapters,
        "ending": quiet.describe() if quiet else None,
        "how_to_check": (
            "Every number above came from a scanned page. Call show_the_page with a "
            "record key to see the exact sentence and the scan it sits on."
        ),
    }
