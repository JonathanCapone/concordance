"""Who was downstream of whom.

In a radio mesh, nodes connect because they can hear each other. Here they
connect because water runs downhill: a treatment plant discharges to a river, and
whatever it discharged arrives at the next town along. That turns a list of
isolated plants into a network, and makes this answerable:

    whose effluent was in your drinking water in 1969?

DOING THIS PROPERLY needs a routed hydrological network -- the National Hydro
Network, flow direction per reach, and the plant's actual outfall rather than the
town centroid. That is not what this module is. It is a defensible approximation
built from two facts:

1. Water Survey station names carry the watercourse: "PINE RIVER NEAR CROOKS",
   "KAMINISTIQUIA RIVER AT MOKOMON". So stations can be grouped by river.
2. `DRAINAGE_AREA_GROSS` is the catchment area upstream of a gauge, and it
   necessarily INCREASES downstream. So gauges on one river can be ordered
   without any flow routing at all.

The approximation is stated on every result rather than buried here, because a
plausible-looking downstream claim about somebody's drinking water is precisely
the kind of output that should not be trusted quietly.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

EARTH_RADIUS_KM = 6371.0

#: Gauges further apart than this are treated as being on different rivers that
#: happen to share a name. Calibrated against real Ontario data -- see the note
#: in downstream_links().
MAX_RIVER_SPREAD_KM = 150.0

#: Words that are not part of a watercourse name.
_LOCATOR = re.compile(
    r"\s+(near|at|above|below|upstream of|downstream of|d/s of|u/s of|outlet of|"
    r"mouth of|en aval de|en amont de)\s+.*$",
    re.I,
)
_WATER_WORD = re.compile(
    r"\b(river|creek|brook|stream|drain|canal|riviere|rivi[eè]re|ruisseau)\b", re.I
)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def watercourse_of(station_name: str) -> str | None:
    """The river a gauge sits on, from its name.

    "KAMINISTIQUIA RIVER AT MOKOMON" -> "kaministiquia river". Returns None when
    the name contains no watercourse word, because a gauge on a lake or a
    reservoir has no downstream ordering in this scheme and should be left out
    rather than guessed at.
    """
    if not station_name:
        return None
    name = _LOCATOR.sub("", str(station_name).strip())
    name = re.sub(r"\s+", " ", name).strip(" ,.")
    if not _WATER_WORD.search(name):
        return None
    # "DAAQUAM (RIVIERE)" -> "daaquam riviere"
    name = re.sub(r"[()]", " ", name)
    return re.sub(r"\s+", " ", name).strip().lower() or None


@dataclass
class Station:
    identifier: str
    name: str
    lat: float
    lon: float
    drainage_area_km2: float | None
    status: str = ""
    watercourse: str | None = None

    @classmethod
    def from_feature(cls, f: dict[str, Any]) -> "Station | None":
        p = f.get("properties") or {}
        g = f.get("geometry") or {}
        coords = g.get("coordinates") or []
        if len(coords) < 2:
            return None
        da = p.get("DRAINAGE_AREA_GROSS")
        return cls(
            identifier=str(p.get("STATION_NUMBER") or p.get("IDENTIFIER") or ""),
            name=str(p.get("STATION_NAME") or ""),
            lat=float(coords[1]),
            lon=float(coords[0]),
            drainage_area_km2=float(da) if isinstance(da, (int, float)) else None,
            status=str(p.get("STATUS_EN") or ""),
            watercourse=watercourse_of(str(p.get("STATION_NAME") or "")),
        )


@dataclass
class PlacedPlant:
    """A treatment plant tied to the nearest gauge on a named watercourse."""

    place: str
    lat: float
    lon: float
    station: Station | None = None
    distance_km: float | None = None

    @property
    def watercourse(self) -> str | None:
        return self.station.watercourse if self.station else None

    @property
    def confidence(self) -> str:
        """How much to trust the river assignment, in words rather than a number.

        Distance to the nearest gauge is the whole of the evidence here, so
        saying so plainly is more honest than a decimal.
        """
        if self.distance_km is None:
            return "not placed"
        if self.distance_km <= 5:
            return "likely"
        if self.distance_km <= 20:
            return "possible"
        return "weak"


def load_stations(geojson: dict[str, Any]) -> list[Station]:
    out = []
    for f in geojson.get("features", []):
        s = Station.from_feature(f)
        if s is not None:
            out.append(s)
    return out


def place_plants(
    plants: Iterable[tuple[str, float, float]],
    stations: list[Station],
    *,
    max_km: float = 40.0,
    dedupe: bool = True,
) -> list[PlacedPlant]:
    """Attach each plant to the nearest gauge that names a watercourse.

    `dedupe` collapses names that denote one place. The corpus supplies
    "Sidney Township (Batawa)", "Sidney Twp.- (Batawa)" and "Sidney (Batawa)"
    as three separate entries on the Trent, and treating one town as three
    plants would invent upstream/downstream relationships between a place and
    itself.
    """
    river_stations = [s for s in stations if s.watercourse]
    out: list[PlacedPlant] = []
    seen_at: dict[tuple[int, int], str] = {}

    for place, lat, lon in plants:
        if dedupe:
            # Same coordinates to ~100 m means the same discharge point.
            fingerprint = (round(lat * 1000), round(lon * 1000))
            if fingerprint in seen_at:
                continue
            seen_at[fingerprint] = place
        best: Station | None = None
        best_d = float("inf")
        for s in river_stations:
            d = haversine_km(lat, lon, s.lat, s.lon)
            if d < best_d:
                best, best_d = s, d
        if best is not None and best_d <= max_km:
            out.append(PlacedPlant(place, lat, lon, best, round(best_d, 2)))
        else:
            out.append(PlacedPlant(place, lat, lon, None, None))
    return out


@dataclass
class DownstreamLink:
    upstream: str
    downstream: str
    watercourse: str
    upstream_drainage_km2: float
    downstream_drainage_km2: float
    confidence: str
    caveat: str = (
        "Inferred from gauge drainage area on a shared watercourse name, not from "
        "a routed hydrological network. Verify against the National Hydro Network "
        "before making any claim about a specific community's water."
    )


def downstream_links(placed: list[PlacedPlant]) -> tuple[list[DownstreamLink], list[str]]:
    """Order plants along each shared watercourse by catchment area.

    Returns (links, warnings). The warnings matter: two rivers in different
    basins can share a name, and this scheme cannot tell them apart on the name
    alone, so any group whose gauges are implausibly far apart is reported rather
    than silently linked.
    """
    by_river: dict[str, list[PlacedPlant]] = {}
    for p in placed:
        if p.watercourse and p.station and p.station.drainage_area_km2:
            by_river.setdefault(p.watercourse, []).append(p)

    links: list[DownstreamLink] = []
    warnings: list[str] = []

    for river, group in sorted(by_river.items()):
        if len(group) < 2:
            continue

        # A shared name across distant gauges is almost certainly two rivers.
        #
        # 150 km is calibrated on this corpus rather than guessed. Across the 19
        # Ontario river groups with two or more plants, the legitimate spreads
        # are: Thames 127 km, Grand 87, Credit 51, South Nation 50, and every
        # other group under 7. The single false positive is the Sydenham at
        # 244 km -- Ontario has two Sydenham Rivers, one draining to Georgian Bay
        # at Owen Sound and one to Lake St. Clair at Wallaceburg, in unconnected
        # watersheds. An earlier 300 km threshold linked them and produced a
        # confident, wrong claim about whose effluent reached whose water.
        #
        # A genuinely long river would be excluded by this, which is why
        # exclusions are reported rather than dropped. Fixing it properly means
        # using basin identifiers from the National Hydro Network instead of
        # river names.
        spread = max(
            haversine_km(a.station.lat, a.station.lon, b.station.lat, b.station.lon)
            for a in group for b in group
        )
        if spread > MAX_RIVER_SPREAD_KM:
            warnings.append(
                f"{river!r}: gauges up to {spread:.0f} km apart across "
                f"{sorted({p.place for p in group})} -- probably different rivers "
                "sharing a name; NOT linked"
            )
            continue

        ordered = sorted(group, key=lambda p: p.station.drainage_area_km2 or 0.0)
        for up, down in zip(ordered, ordered[1:]):
            up_da = up.station.drainage_area_km2 or 0.0
            down_da = down.station.drainage_area_km2 or 0.0
            if down_da <= up_da:
                continue
            # Two gauges with near-identical catchments are effectively the same
            # point on the river and cannot be ordered.
            ratio = down_da / up_da if up_da else float("inf")
            conf = "likely" if ratio > 1.2 else "weak"
            links.append(
                DownstreamLink(
                    upstream=up.place,
                    downstream=down.place,
                    watercourse=river,
                    upstream_drainage_km2=up_da,
                    downstream_drainage_km2=down_da,
                    confidence=conf,
                )
            )
    return links, warnings


def who_was_upstream(links: list[DownstreamLink], place: str) -> list[dict[str, Any]]:
    """Everyone discharging above a given town, transitively.

    This is the tool behind "whose effluent was in your drinking water" -- and it
    returns the caveat with every hop, because the answer is an inference about a
    real community's water supply and must never be presented as established.
    """
    want = place.strip().lower()
    out: list[dict[str, Any]] = []
    seen = {want}
    frontier = [want]

    while frontier:
        current = frontier.pop()
        for link in links:
            if link.downstream.strip().lower() != current:
                continue
            up = link.upstream.strip().lower()
            if up in seen:
                continue
            seen.add(up)
            frontier.append(up)
            out.append({
                "upstream_of": place,
                "place": link.upstream,
                "watercourse": link.watercourse,
                "confidence": link.confidence,
                "caveat": link.caveat,
            })
    return out
