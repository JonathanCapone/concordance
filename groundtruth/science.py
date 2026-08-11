"""Statistics for a record read off paper.

Adapted from the OMEGA-wave inference suite (Mann-Kendall / Theil-Sen, Pettitt
changepoint), which is pure-stdlib and so lifts here without costing this
package its zero-dependency guarantee.

Three things had to change, and they are the reason this is an adaptation
rather than a copy:

1. **n is tiny.** OMEGA bin-averages hundreds of sensor samples and inflates the
   Mann-Kendall variance to damp autocorrelation. An annual report gives one
   value per year -- Owen Sound has ten. Autocorrelation inflation is
   meaningless at that size and would only destroy what little power there is,
   so it is dropped and the small-sample normal approximation is used instead.

2. **Every value carries a reading confidence.** A sensor's error comes from a
   spec sheet; these come from how legible a 1969 scan was and how sure a model
   was about the sentence. That uncertainty has to reach the slope, or a trend
   computed from barely-legible pages looks exactly as authoritative as one
   computed from clean ones. `trend()` therefore reports a bootstrap interval in
   which each point's inclusion is weighted by its confidence.

3. **Silence is a result, not a gap to interpolate.** Nothing here fills a
   missing year. A town that stopped reporting has not got a flat line; it has
   an absence, and the absence is the finding.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Sequence

from .models import Record


# --------------------------------------------------------------------------
# core statistics
# --------------------------------------------------------------------------

def _theil_sen(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Median of pairwise slopes. Robust to the outliers OCR inevitably makes."""
    slopes: list[float] = []
    n = len(xs)
    for i in range(n - 1):
        for j in range(i + 1, n):
            dx = xs[j] - xs[i]
            if dx != 0:
                slopes.append((ys[j] - ys[i]) / dx)
    if not slopes:
        return 0.0
    slopes.sort()
    mid = len(slopes) // 2
    if len(slopes) % 2:
        return slopes[mid]
    return (slopes[mid - 1] + slopes[mid]) / 2.0


def _mann_kendall(ys: Sequence[float]) -> tuple[int, float, float]:
    """Returns (S, z, p) using the tie-corrected small-sample normal approximation.

    No autocorrelation inflation: with one observation per year there is no
    high-frequency structure to damp, and inflating the variance on n=10 would
    simply guarantee "no significant trend" regardless of the data.
    """
    n = len(ys)
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            d = ys[j] - ys[i]
            s += (d > 0) - (d < 0)

    counts: dict[float, int] = {}
    for y in ys:
        counts[y] = counts.get(y, 0) + 1
    tie_term = sum(c * (c - 1) * (2 * c + 5) for c in counts.values() if c > 1)
    var_s = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0
    if var_s <= 0:
        return s, 0.0, 1.0

    if s > 0:
        z = (s - 1) / math.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / math.sqrt(var_s)
    else:
        z = 0.0
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0))))
    return s, z, min(1.0, p)


# --------------------------------------------------------------------------
# trend, with reading uncertainty carried through
# --------------------------------------------------------------------------

@dataclass
class Trend:
    ok: bool
    reason: str = ""
    n: int = 0
    direction: str = ""
    significant: bool = False
    p_value: float = 1.0
    slope_per_year: float = 0.0
    #: 5th-95th percentile of the bootstrap slope distribution. Widens as the
    #: underlying readings get less confident -- this is where scan legibility
    #: actually reaches the answer.
    slope_ci90: tuple[float, float] = (0.0, 0.0)
    #: Fraction of bootstrap replicates agreeing with the point-estimate
    #: direction. Below ~0.9 the trend is not robust to reading uncertainty
    #: even when the p-value looks respectable.
    direction_stability: float = 0.0
    mean_confidence: float = 0.0
    span: tuple[float, float] = (0.0, 0.0)

    def describe(self) -> str:
        if not self.ok:
            return f"no trend computed: {self.reason}"
        lo, hi = self.slope_ci90
        out = (
            f"{self.direction} {self.slope_per_year:+.3g}/yr "
            f"(90% CI {lo:+.3g} to {hi:+.3g}, n={self.n}, p={self.p_value:.3f})"
        )
        if not self.significant:
            out += " -- not significant"
        if self.direction_stability < 0.9:
            out += (
                f" -- UNSTABLE: only {self.direction_stability:.0%} of replicates "
                "agree on direction once reading confidence is accounted for"
            )
        return out


def trend(
    points: Sequence[tuple[float, float, float]],
    *,
    bootstrap: int = 500,
    min_n: int = 6,
    seed: int = 12345,
) -> Trend:
    """Monotonic trend over (time, value, confidence) triples.

    `time` is in years (a float, so 1969.5 is mid-year). Confidence is 0..1 and
    weights how often a point survives into a bootstrap replicate, so a series
    read off illegible scans yields a visibly wider interval rather than a
    falsely crisp slope.
    """
    pts = [(float(t), float(v), max(0.0, min(1.0, float(c)))) for t, v, c in points]
    pts.sort(key=lambda p: p[0])
    n = len(pts)
    if n < min_n:
        return Trend(ok=False, reason=f"only {n} readings; need {min_n}", n=n)

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    confs = [p[2] for p in pts]

    s, _z, p = _mann_kendall(ys)
    slope = _theil_sen(xs, ys)
    direction = "increasing" if s > 0 else "decreasing" if s < 0 else "flat"

    rng = random.Random(seed)
    slopes: list[float] = []
    for _ in range(bootstrap):
        # Weighted resample: a low-confidence reading is simply less likely to
        # be in this replicate. Cheap, assumption-light, and it degrades in the
        # right direction as the corpus gets harder to read.
        sample = [pts[rng.randrange(n)] for _ in range(n)]
        keep = [q for q in sample if rng.random() <= q[2]]
        if len(keep) < 3:
            continue
        keep.sort(key=lambda q: q[0])
        bxs = [q[0] for q in keep]
        bys = [q[1] for q in keep]
        if len(set(bxs)) < 2:
            continue
        slopes.append(_theil_sen(bxs, bys))

    if len(slopes) < 20:
        return Trend(
            ok=False,
            reason="reading confidence too low to bootstrap a stable slope",
            n=n,
            mean_confidence=sum(confs) / n,
        )

    slopes.sort()
    lo = slopes[int(0.05 * (len(slopes) - 1))]
    hi = slopes[int(0.95 * (len(slopes) - 1))]
    if slope > 0:
        agree = sum(1 for x in slopes if x > 0)
    elif slope < 0:
        agree = sum(1 for x in slopes if x < 0)
    else:
        agree = sum(1 for x in slopes if x == 0)

    return Trend(
        ok=True,
        n=n,
        direction=direction,
        significant=p < 0.05,
        p_value=p,
        slope_per_year=slope,
        slope_ci90=(lo, hi),
        direction_stability=agree / len(slopes),
        mean_confidence=sum(confs) / n,
        span=(xs[0], xs[-1]),
    )


# --------------------------------------------------------------------------
# changepoint
# --------------------------------------------------------------------------

@dataclass
class Changepoint:
    ok: bool
    reason: str = ""
    detected: bool = False
    at: float = 0.0
    p_value: float = 1.0
    mean_before: float = 0.0
    mean_after: float = 0.0
    shift: float = 0.0
    n: int = 0


def changepoint(points: Sequence[tuple[float, float]], *, min_n: int = 8) -> Changepoint:
    """Pettitt test: the single most likely shift in the median.

    Rank-based and unit-free, so it survives the mixed units and outliers that
    fall out of reading sixty-year-old prose. `min_n` is lowered from OMEGA's 12
    because annual series are short by nature -- a plant with twelve years of
    reports is one of the better-documented ones in the corpus.

    LIMITATION, measured: the standard p-value approximation
    ``2*exp(-6K^2 / (n^3 + n^2))`` is markedly conservative at small n. On a
    ten-point series stepping 177 -> 90 -- a halving, obvious to the eye -- it
    returns p = 0.066 and therefore "not detected" at 95%.

    So a null result here is close to meaningless for annual data, and
    `detected` must never be read as "no change occurred". Use `shift`,
    `mean_before` and `mean_after` for the magnitude, treat `p_value` as a weak
    ordering signal between candidate changepoints, and say so wherever a result
    is published. Fixing this properly needs either a permutation test or exact
    small-sample critical values; until then the honest move is to report the
    shift and let a human look at the scans.
    """
    pts = sorted(((float(t), float(v)) for t, v in points), key=lambda p: p[0])
    n = len(pts)
    if n < min_n:
        return Changepoint(ok=False, reason=f"only {n} readings; need {min_n}", n=n)
    vals = [p[1] for p in pts]

    order = sorted(range(n), key=lambda i: vals[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1

    cum = 0.0
    best_u = 0.0
    best_t = 0
    for t_idx in range(1, n):
        cum += ranks[t_idx - 1]
        u = 2.0 * cum - t_idx * (n + 1)
        if abs(u) > abs(best_u):
            best_u, best_t = u, t_idx

    k_stat = abs(best_u)
    p = min(1.0, 2.0 * math.exp((-6.0 * k_stat * k_stat) / (n ** 3 + n ** 2)))
    before = vals[:best_t]
    after = vals[best_t:]
    mb = sum(before) / len(before)
    ma = sum(after) / len(after)
    return Changepoint(
        ok=True,
        detected=p < 0.05,
        at=pts[best_t][0],
        p_value=p,
        mean_before=mb,
        mean_after=ma,
        shift=ma - mb,
        n=n,
    )


# --------------------------------------------------------------------------
# the negative record
# --------------------------------------------------------------------------

@dataclass
class Silence:
    """What stopped being measured, and when.

    Nothing here interpolates. In a live network a quiet station is a fault to
    fix; in an archive it is history, and filling it in would erase the finding.
    """

    place: str
    first_year: int
    last_year: int
    reported_years: list[int] = field(default_factory=list)
    missing_years: list[int] = field(default_factory=list)
    #: Years after the last report, up to the corpus horizon. Distinguished from
    #: interior gaps because "stopped reporting" and "skipped a year" are
    #: different events.
    silent_since: int | None = None
    longest_gap: int = 0

    @property
    def continuity(self) -> float:
        span = self.last_year - self.first_year + 1
        return len(self.reported_years) / span if span > 0 else 0.0

    def describe(self) -> str:
        out = (
            f"{self.place}: {len(self.reported_years)} reports "
            f"{self.first_year}-{self.last_year} ({self.continuity:.0%} continuity)"
        )
        if self.longest_gap > 1:
            out += f", longest interior gap {self.longest_gap} yr"
        if self.silent_since is not None:
            out += f", SILENT since {self.silent_since}"
        return out


def silence(
    place: str,
    years: Sequence[int],
    *,
    horizon: int | None = None,
) -> Silence:
    """Reporting continuity for one place.

    `horizon` is the last year the corpus could plausibly cover. Without it,
    "silent since" cannot be distinguished from "the archive simply ends here",
    so it is only reported when a horizon is supplied.

    IMPORTANT: a gap here means *not digitised or not reported*. Those are not
    the same thing, and no claim of institutional silence is safe until the gap
    has been checked against what the archive actually holds.
    """
    ys = sorted(set(int(y) for y in years))
    if not ys:
        return Silence(place=place, first_year=0, last_year=0)

    first, last = ys[0], ys[-1]
    missing = [y for y in range(first, last + 1) if y not in set(ys)]

    longest = 0
    run = 0
    for y in range(first, last + 1):
        if y in set(ys):
            run = 0
        else:
            run += 1
            longest = max(longest, run)

    silent_since = None
    if horizon is not None and last < horizon:
        silent_since = last + 1

    return Silence(
        place=place,
        first_year=first,
        last_year=last,
        reported_years=ys,
        missing_years=missing,
        silent_since=silent_since,
        longest_gap=longest,
    )


# --------------------------------------------------------------------------
# observations against the standard of their own era
# --------------------------------------------------------------------------

@dataclass
class Exceedance:
    parameter: str
    n_observations: int
    n_exceeding: int
    standard_value: float
    standard_unit: str
    standard_year: int | None
    exceeding_years: list[int] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return self.n_exceeding / self.n_observations if self.n_observations else 0.0


def exceedance(
    observations: Sequence[tuple[int, float]],
    standard_value: float,
    *,
    parameter: str,
    unit: str,
    standard_year: int | None = None,
) -> Exceedance:
    """How often observations breached a limit.

    The caller must supply the standard **contemporary with the observations**.
    Judging a 1969 reading against a 2020 guideline is a category error that
    produces a damning and meaningless result, which is why `standard_year` is
    recorded on the output rather than left implicit.
    """
    over = [y for y, v in observations if v > standard_value]
    return Exceedance(
        parameter=parameter,
        n_observations=len(observations),
        n_exceeding=len(over),
        standard_value=standard_value,
        standard_unit=unit,
        standard_year=standard_year,
        exceeding_years=sorted(over),
    )


# --------------------------------------------------------------------------
# convenience: pull a series straight out of extracted records
# --------------------------------------------------------------------------

@dataclass
class Series:
    """A comparable run of readings, plus everything that had to be assumed.

    `assumptions`, `rejected` and `suspect` are part of the result, not
    diagnostics to be logged away. A series that quietly dropped a third of its
    points, silently converted Imperial gallons, or contains a scan corruption is
    not the same object as one that doesn't, and a reader has to be able to tell.
    """

    parameter: str
    stream: str | None
    points: list[tuple[float, float, float]] = field(default_factory=list)
    unit: str = ""
    assumptions: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    #: Readings that are still in `points` but look wrong. Flagged rather than
    #: removed: a plant really can have a bad year, and deleting inconvenient
    #: data is a worse failure than reporting it with a warning attached.
    suspect: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.points)


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def find_suspect_readings(points: list[tuple[float, float, float]]) -> list[str]:
    """Flag readings that look like scan corruption rather than measurement.

    The 1968 Owen Sound report is the motivating case. Its OCR reads

        "The total flow to the plant in 1968 was 144:2. 50 million gallons"

    where the document says 1442.50. The model faithfully returned 144.2, which
    sits an order of magnitude below every neighbouring year and is entirely
    plausible in isolation.

    A dropped or misplaced digit is the characteristic OCR failure on these
    scans, so a point that would land near the series median if multiplied by a
    power of ten is called out specifically. That is a much stronger signal than
    "this is an outlier", and it tells a reader exactly what to look for on the
    page.
    """
    if len(points) < 3:
        return []
    values = [v for _, v, _ in points]
    med = _median(values)
    if med == 0:
        return []
    deviations = [abs(v - med) for v in values]
    mad = _median(deviations)

    out: list[str] = []
    for year, value, _conf in points:
        if value == 0:
            continue
        # Robust outlier test. 4.45 MAD is roughly 3 sigma for normal data;
        # the constant matters less than using MAD rather than a mean and
        # standard deviation, which a single bad point would drag with it.
        far = mad > 0 and abs(value - med) > 4.45 * mad
        if not far and abs(value - med) <= abs(med):
            continue

        for power in (-3, -2, -1, 1, 2, 3):
            shifted = value * (10 ** power)
            if abs(shifted - med) <= 0.5 * abs(med):
                out.append(
                    f"{int(year)}: {value:g} is ~10^{power} from the series median "
                    f"({med:g}); a dropped or misplaced digit in the scan would "
                    f"explain it. Check the page before using this point."
                )
                break
        else:
            if far:
                out.append(
                    f"{int(year)}: {value:g} is far from the series median ({med:g}). "
                    "Could be a genuinely unusual year or a misreading; check the page."
                )
    return out


def series_from_records(
    records: Sequence[Record],
    *,
    parameter: str,
    stream: str | None = None,
    kind: str = "observation",
) -> Series:
    """Build one comparable series for a parameter, reconciling units.

    Filters to a single `kind` by default. Mixing an `observation` series with
    `design` values would chart a plant's engineered capacity as though someone
    had measured it.

    Units are reconciled through the methods-drift layer rather than assumed
    equal, because the corpus writes the same quantity several ways across
    decades -- "180 PPM" in 1963 and "180 mg/1" in 1969 are one specification,
    while "million Imperial gallons per day" and a bare "gallons" are not one
    unit. Readings that cannot honestly be compared are rejected and reported,
    never coerced into the series.
    """
    from .parameters import resolve as resolve_param  # local imports keep this
    from .units import normalize_series                # module acyclic

    # Match on the resolved parameter, never on a substring of its name.
    # Substring matching put removal percentages into the effluent-concentration
    # chart, because "suspended solids" is inside "suspended solids removal" and
    # both are small numbers that fall when a plant improves.
    want_param = resolve_param(parameter)
    want = parameter.lower()

    raw: list[tuple[float, float, str | None, float]] = []
    for r in records:
        if r.kind != kind or r.value is None:
            continue
        got = resolve_param(r.parameter, r.unit)
        if want_param is not None:
            if got is None or got.key != want_param.key:
                continue
        elif want not in r.parameter.lower():
            # The requested parameter isn't in the table; fall back to substring
            # matching rather than returning nothing, but only in that case.
            continue
        if stream is not None and r.stream != stream:
            continue
        if not r.period:
            continue
        try:
            year = float(str(r.period)[:4])
        except ValueError:
            continue
        raw.append((year, float(r.value), r.unit, float(r.confidence)))

    points, assumptions, rejected = normalize_series(raw, parameter=parameter)

    unit = ""
    if points:
        from .units import to_base
        for _y, _v, _c in points:
            break
        # Report the base unit the series settled on, for labelling a chart axis.
        for _year, _value, _u, _conf in raw:
            q = to_base(1.0, _u)
            if q is not None:
                unit = q.unit
                break

    # One report per year: keep the most confident reading rather than letting a
    # page that states a value twice weight it double.
    best: dict[float, tuple[float, float, float]] = {}
    for y, v, c in points:
        if y not in best or c > best[y][2]:
            best[y] = (y, v, c)

    final = sorted(best.values())
    return Series(
        parameter=parameter,
        stream=stream,
        points=final,
        unit=unit,
        assumptions=assumptions,
        rejected=rejected,
        suspect=find_suspect_readings(final),
    )
