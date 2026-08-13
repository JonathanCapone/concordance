"""Era-aware Ontario place resolution for document-title labels.

Current names come from a compact, offline derivative of Natural Resources
Canada's CGNDB.  Former municipalities are separate curated records: replacing
Fort William with Thunder Bay on a 1965 measurement would rewrite the historical
fact the resolver exists to preserve.

The resolver is deliberately exact and structural, not fuzzy.  Ontario contains
several official places with the same normalized name, and an attractive typo
correction can put a plant in the wrong watershed while still looking plausible.
"""

from __future__ import annotations

import csv
import json
import os
import re
import unicodedata
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class Place:
    """One conservative interpretation of a title-derived Ontario place name."""

    canonical: str
    lat: float | None
    lon: float | None
    kind: str
    province: str
    confidence: float
    as_of_year: int | None
    superseded_by: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class _Candidate:
    id: str
    name: str
    generic_term: str
    generic_category: str
    concise_code: str
    lat: float
    lon: float
    location: str
    decision_date: str


_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "gazetteer"
_FACILITY_TAIL = re.compile(
    r"\s*(?::|,)?\s*(water\s+(?:treatment\s+plant|supply\s+system))\s+and\s*$",
    re.IGNORECASE,
)
_CAMBRIDGE_LOCALITY = re.compile(
    r"^\s*cambridge\s*\(\s*(galt|preston|hespeler)\s*\)\s*$",
    re.IGNORECASE,
)

_TERM_PRIORITY = {
    "city": 0,
    "town": 1,
    "village municipality": 2,
    "village": 2,
    "urban community": 3,
    "suburban community": 4,
    "compact rural community": 5,
    "community": 6,
    "settlement": 7,
    "dispersed rural community": 8,
    "railway point": 20,
}


def _data_dir() -> Path:
    override = os.environ.get("GROUNDTRUTH_GAZETTEER_DIR")
    return Path(override) if override else _DEFAULT_DATA_DIR


def _key(text: str) -> str:
    """Comparison key only; administrative words are never discarded."""
    decomposed = unicodedata.normalize("NFKD", text)
    unaccented = "".join(char for char in decomposed if not unicodedata.combining(char))
    lowered = unaccented.casefold().replace("&", " and ")
    words = re.sub(r"[^a-z0-9]+", " ", lowered).split()
    return " ".join("township" if word == "twp" else word for word in words)


def _float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"invalid CGNDB coordinate: {value!r}") from exc


@lru_cache(maxsize=1)
def _candidates() -> tuple[dict[str, tuple[_Candidate, ...]], dict[str, _Candidate]]:
    path = _data_dir() / "cgn_on_places.csv"
    by_name: dict[str, list[_Candidate]] = {}
    by_id: dict[str, _Candidate] = {}
    try:
        handle = path.open(encoding="utf-8", newline="")
    except OSError as exc:
        raise RuntimeError(
            f"Ontario gazetteer is missing: {path}. "
            "Run scripts/build_gazetteer.py from the source checkout."
        ) from exc

    with handle:
        for row in csv.DictReader(handle):
            candidate = _Candidate(
                id=row["id"],
                name=row["name"],
                generic_term=row["generic_term"],
                generic_category=row["generic_category"],
                concise_code=row["concise_code"],
                lat=_float(row["lat"]),
                lon=_float(row["lon"]),
                location=row["location"],
                decision_date=row["decision_date"],
            )
            by_name.setdefault(_key(candidate.name), []).append(candidate)
            by_id[candidate.id] = candidate

    return ({key: tuple(rows) for key, rows in by_name.items()}, by_id)


def _load_json(name: str) -> dict[str, Any]:
    path = _data_dir() / name
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot load gazetteer data: {path} ({exc})") from exc
    if payload.get("schema_version") != 1:
        raise RuntimeError(f"unsupported gazetteer schema in {path}")
    return payload


@lru_cache(maxsize=1)
def _alias_data() -> tuple[dict[str, dict[str, Any]], frozenset[str]]:
    payload = _load_json("aliases.json")
    aliases: dict[str, dict[str, Any]] = {}
    for entry in payload.get("entries", []):
        has_lat = entry.get("lat") is not None
        has_lon = entry.get("lon") is not None
        if has_lat != has_lon:
            raise RuntimeError(
                f"gazetteer alias has only one coordinate: {entry.get('canonical')}"
            )
        if has_lat and not entry.get("source"):
            raise RuntimeError(
                f"coordinate-bearing alias lacks a source: {entry.get('canonical')}"
            )
        for name in entry.get("names", []):
            lookup = _key(name)
            if lookup in aliases and aliases[lookup] is not entry:
                raise RuntimeError(f"duplicate gazetteer alias: {name}")
            aliases[lookup] = entry
    non_places = frozenset(_key(name) for name in payload.get("non_places", []))
    return aliases, non_places


@lru_cache(maxsize=1)
def _history_data() -> dict[str, dict[str, Any]]:
    payload = _load_json("amalgamations.json")
    entries: dict[str, dict[str, Any]] = {}
    for entry in payload.get("entries", []):
        if not entry.get("sources"):
            raise RuntimeError(f"historical entry lacks a source: {entry.get('canonical')}")
        for name in entry.get("names", []):
            lookup = _key(name)
            if lookup in entries:
                raise RuntimeError(f"duplicate historical place: {name}")
            entries[lookup] = entry
    return entries


def _kind(candidate: _Candidate) -> str:
    term = candidate.generic_term.casefold()
    if "township" in term:
        return "township"
    # Concise codes preserve the municipal class when the generic term is a
    # qualified form such as "Separated Town".
    if candidate.concise_code == "CITY":
        return "city"
    if candidate.concise_code == "TOWN":
        return "town"
    if candidate.concise_code == "VILG" or "village" in term:
        return "village"
    return "unknown"


def _candidate_place(
    candidate: _Candidate,
    year: int | None,
    *,
    canonical: str | None = None,
    kind: str | None = None,
    confidence: float = 0.97,
    note: str | None = None,
    superseded_by: str | None = None,
) -> Place:
    return Place(
        canonical=canonical or candidate.name,
        lat=candidate.lat,
        lon=candidate.lon,
        kind=kind or _kind(candidate),
        province="ON",
        confidence=max(0.0, min(1.0, confidence)),
        as_of_year=year,
        superseded_by=superseded_by,
        note=note,
    )


def _historical_place(entry: dict[str, Any], year: int | None) -> Place:
    # Some reorganizations kept the same public name while changing the entity
    # and reference point. Meaford therefore cannot be represented by one
    # validity interval plus a successor name.
    if year is not None:
        for period in entry.get("resolution_periods", []):
            starts_in = period.get("valid_from")
            ends_in = period.get("valid_to")
            if (starts_in is None or year >= int(starts_in)) and (
                ends_in is None or year <= int(ends_in)
            ):
                selected = dict(entry)
                selected.update(period)
                selected.pop("resolution_periods", None)
                return _historical_place(selected, year)

    canonical = str(entry["canonical"])
    kind = str(entry["kind"])
    for period in entry.get("kind_periods", []):
        starts_in = period.get("valid_from")
        ends_in = period.get("valid_to")
        if year is not None and (starts_in is None or year >= int(starts_in)) and (
            ends_in is None or year <= int(ends_in)
        ):
            kind = str(period["kind"])
            break
    valid_from = entry.get("valid_from")
    valid_to = entry.get("valid_to")
    event_note = str(entry["event_note"])
    confidence = 0.99

    if year is None:
        note = event_note[0].upper() + event_note[1:] + "."
    elif valid_from is not None and year < int(valid_from):
        note = (
            f"{canonical} did not exist as a {kind} in {year}; "
            f"it was {event_note}."
        )
        confidence = 0.65
    elif valid_to is not None and year > int(valid_to):
        entity = (
            f"a separate {kind}" if kind != "unknown" else "a separate municipality"
        )
        note = (
            f"{canonical} no longer existed as {entity} in {year}; "
            f"it was {event_note}."
        )
        confidence = 0.9
    elif entry.get("superseded_by"):
        note = (
            f"{canonical} was a separate {kind} in {year}; "
            f"it was later {event_note}."
        )
    else:
        note = f"{canonical} was valid in {year}; it was {event_note}."

    coordinate_note = entry.get("coordinate_note")
    if coordinate_note:
        note = f"{note} {coordinate_note}"

    return Place(
        canonical=canonical,
        lat=float(entry["lat"]) if entry.get("lat") is not None else None,
        lon=float(entry["lon"]) if entry.get("lon") is not None else None,
        kind=kind,
        province="ON",
        confidence=confidence,
        as_of_year=year,
        superseded_by=entry.get("superseded_by"),
        note=note,
    )


def _alias_place(entry: dict[str, Any], year: int | None) -> Place:
    canonical = str(entry["canonical"])
    candidate_id = entry.get("candidate_id")
    candidate = _candidates()[1].get(str(candidate_id)) if candidate_id else None
    note = entry.get("note")

    if candidate_id and candidate is None:
        raise RuntimeError(
            f"gazetteer alias {canonical!r} references missing CGNDB ID "
            f"{candidate_id!r}"
        )

    history_name = str(entry.get("history_name", canonical))
    history = _history_data().get(_key(history_name))
    if history is not None:
        selected_history = history
        if candidate is not None and (
            candidate.lat != history.get("lat") or candidate.lon != history.get("lon")
        ):
            selected_history = dict(history)
            selected_history.pop("coordinate_note", None)
        place = _historical_place(selected_history, year)
        latitude, longitude = place.lat, place.lon
        if candidate is not None:
            latitude, longitude = candidate.lat, candidate.lon
        elif entry.get("lat") is not None:
            latitude = float(entry["lat"])
            longitude = float(entry["lon"])
        place = replace(
            place,
            canonical=canonical,
            lat=latitude,
            lon=longitude,
            confidence=min(place.confidence, float(entry.get("confidence", 1.0))),
        )
        return _append_note(place, str(note)) if note else place

    if candidate is None:
        return Place(
            canonical=canonical,
            lat=float(entry["lat"]) if entry.get("lat") is not None else None,
            lon=float(entry["lon"]) if entry.get("lon") is not None else None,
            kind=str(entry.get("kind", "unknown")),
            province="ON",
            confidence=float(entry.get("confidence", 0.4)),
            as_of_year=year,
            superseded_by=None,
            note=str(note) if note else None,
        )

    return _candidate_place(
        candidate,
        year,
        canonical=canonical,
        kind=str(entry.get("kind") or _kind(candidate)),
        confidence=float(entry.get("confidence", 0.9)),
        note=str(note) if note else None,
        superseded_by=None,
    )


def _ambiguous(name: str, year: int | None, note: str) -> Place:
    return Place(
        canonical=" ".join(name.split()),
        lat=None,
        lon=None,
        kind="unknown",
        province="ON",
        confidence=0.35,
        as_of_year=year,
        note=note,
    )


def _township_candidates(lookup: str) -> tuple[str, list[_Candidate]] | None:
    base: str | None = None
    if lookup.endswith(" township"):
        base = lookup.removesuffix(" township")
    elif lookup.startswith("township of "):
        base = lookup.removeprefix("township of ")
    if not base:
        return None

    rows = [
        row
        for row in _candidates()[0].get(base, ())
        if row.generic_category == "Administrative Area"
        and "township" in row.generic_term.casefold()
    ]
    return base, rows


def _choose_township(name: str, lookup: str, year: int | None) -> Place | None:
    parsed = _township_candidates(lookup)
    if parsed is None:
        return None
    base, rows = parsed
    if not rows:
        return _ambiguous(
            name,
            year,
            f"The title says township, but CGNDB has no matching Ontario township for {base!r}.",
        )

    # A municipality is the relevant entity for a municipal plant report; a
    # geographic township is only selected when no municipal record exists.
    municipal = [row for row in rows if row.concise_code == "MUN2"]
    eligible = municipal or rows
    if len(eligible) != 1:
        return _ambiguous(
            name,
            year,
            f"CGNDB contains {len(eligible)} township candidates with this name.",
        )
    candidate = eligible[0]
    return _candidate_place(
        candidate,
        year,
        canonical=f"{candidate.name} Township",
        kind="township",
        confidence=0.99 if municipal else 0.96,
    )


def _choose_populated(name: str, lookup: str, year: int | None) -> Place | None:
    rows = [
        row
        for row in _candidates()[0].get(lookup, ())
        if row.generic_category == "Populated Place"
    ]
    if not rows:
        return None

    priorities = [(_TERM_PRIORITY.get(row.generic_term.casefold(), 10), row) for row in rows]
    best_priority = min(priority for priority, _ in priorities)
    best = [row for priority, row in priorities if priority == best_priority]
    if len(best) != 1:
        return _ambiguous(
            name,
            year,
            f"CGNDB contains {len(best)} equally plausible populated places with this name.",
        )

    candidate = best[0]
    note = None
    confidence = 0.99 if candidate.concise_code in {"CITY", "TOWN"} else 0.96
    if len(rows) > 1:
        confidence = min(confidence, 0.9)
        note = (
            f"Selected the CGNDB {candidate.generic_term.lower()} among "
            f"{len(rows)} Ontario populated features with this name."
        )
    try:
        decision_year = int(candidate.decision_date[:4])
    except (TypeError, ValueError):
        decision_year = None
    if year is not None and decision_year is not None and decision_year > year:
        confidence = min(confidence, 0.85)
        caution = (
            f"The CGNDB naming decision is dated {decision_year}; the reference "
            f"point is usable, but that date does not establish the place's "
            f"municipal class in {year}."
        )
        note = f"{note} {caution}" if note else caution
    return _candidate_place(candidate, year, confidence=confidence, note=note)


def _append_note(place: Place, addition: str, *, confidence_factor: float = 1.0) -> Place:
    note = f"{place.note} {addition}" if place.note else addition
    return replace(
        place,
        confidence=round(place.confidence * confidence_factor, 4),
        note=note,
    )


def _curated_scope_contains_place(place: str, file_place: str) -> bool:
    """Return whether a curated file label explicitly embeds this locality.

    Composite report labels such as ``Burlington Elizabeth Gardens`` point to
    a specific CGNDB candidate in ``aliases.json``.  That explicit link is
    strong enough to keep ``Elizabeth Gardens`` as the facility/locality under
    the file label.  Mere text containment is not: ``Arthur`` and historical
    ``Port Arthur`` are distinct populated places despite sharing a word.
    """
    entry = _alias_data()[0].get(_key(file_place))
    candidate_id = entry.get("candidate_id") if entry is not None else None
    candidate = _candidates()[1].get(str(candidate_id)) if candidate_id else None
    return candidate is not None and _key(candidate.name) == _key(place)


def resolve(name: str, year: int | None = None) -> Place | None:
    """Resolve an Ontario title label, or return ``None`` when it is not a place.

    Unknown strings are not fuzzy-matched.  A known composite can return a
    low-confidence ``Place`` without coordinates; this makes ambiguity visible
    without pretending a joint service area has one authoritative point.
    """
    if not isinstance(name, str) or not name.strip():
        return None
    if year is not None and (isinstance(year, bool) or not isinstance(year, int)):
        raise TypeError("year must be an int or None")

    lookup = _key(name)
    aliases, non_places = _alias_data()
    if lookup in non_places:
        return None

    locality_match = _CAMBRIDGE_LOCALITY.fullmatch(name)
    if locality_match:
        locality = locality_match.group(1)
        historical = _history_data().get(_key(locality))
        if historical is None:
            return None
        place = _historical_place(historical, year)
        return _append_note(
            place,
            f"The title preserves the {locality.title()} locality within Cambridge.",
        )

    historical = _history_data().get(lookup)
    if historical is not None:
        return _historical_place(historical, year)

    alias = aliases.get(lookup)
    if alias is not None:
        return _alias_place(alias, year)

    facility_match = _FACILITY_TAIL.search(name)
    if facility_match:
        base = name[: facility_match.start()].strip(" ,:-")
        place = resolve(base, year)
        if place is None:
            return None
        facility = " ".join(facility_match.group(1).lower().split())
        return _append_note(
            place,
            f"Recovered from a truncated {facility} document title.",
            confidence_factor=0.96,
        )

    township = _choose_township(name, lookup, year)
    if township is not None:
        return township
    return _choose_populated(name, lookup, year)


def scope_record_location(
    place: str | None,
    file_place: str | None,
    facility: str | None,
    year: int | None = None,
) -> tuple[str | None, str | None]:
    """Keep a record inside its extraction scope without losing what it named.

    A municipality result file is the strong context. Models nevertheless put
    plant names (``Brantford Water Treatment Plant``), equipment (``digesters``)
    and site labels (``Site 1``) in the place field. If the candidate is not a
    populated place, or it resolves to the same municipality as the file, the
    file label becomes the place and the more specific wording is preserved as
    a facility when no better facility was already extracted.

    A genuinely different populated place is retained. Reports can compare
    municipalities, and file scope is not permission to erase that evidence.
    """
    raw = " ".join(str(place or "").split()) or None
    scope = " ".join(str(file_place or "").split()) or None
    specific = " ".join(str(facility or "").split()) or None
    if scope is None:
        return raw, specific
    if raw is None or raw.casefold() == scope.casefold():
        return scope, specific

    resolved_raw = resolve(raw, year)
    resolved_scope = resolve(scope, year)
    same_entity = bool(
        resolved_raw is not None
        and resolved_scope is not None
        and resolved_raw.canonical.casefold() == resolved_scope.canonical.casefold()
    )
    # A curated file label can explicitly include a locality that also resolves
    # independently (Elizabeth Gardens inside Burlington). Text containment by
    # itself is insufficient: Arthur and Port Arthur are different places.
    curated_relation = _curated_scope_contains_place(raw, scope)
    if resolved_raw is None or same_entity or curated_relation:
        return scope, specific or raw
    return raw, specific


def scope_record_dict(
    record: Mapping[str, Any],
    file_place: str | None,
) -> dict[str, Any]:
    """Return one record with its location interpreted in its file's scope.

    Result files are the durable boundary that says which municipality or site
    an extraction belongs to.  Every reader of those files must apply the same
    transformation before computing record identities or dispute slots.  If
    the portal normalises a record but export/dedup keeps the raw model field,
    the same reading becomes two different claims on a round trip.

    The model's original wording remains in ``raw.reported_place`` whenever
    scoping changes it.  Callers receive a copy; source evidence on disk is not
    rewritten.
    """
    scoped = dict(record)
    period = scoped.get("period")
    year = None
    try:
        year = int(str(period)[:4])
    except (TypeError, ValueError):
        pass
    place, facility = scope_record_location(
        scoped.get("place"), file_place, scoped.get("facility"), year,
    )
    raw = dict(scoped.get("raw") or {})
    reported_place = " ".join(str(scoped.get("place") or "").split())
    if reported_place and place != reported_place:
        raw.setdefault("reported_place", reported_place)
    scoped["place"] = place
    scoped["facility"] = facility
    scoped["raw"] = raw
    return scoped


__all__ = ["Place", "resolve", "scope_record_dict", "scope_record_location"]
