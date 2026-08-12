"""Did what one town discharged show up in the next town's water?

The watershed module establishes who was downstream of whom. This one asks the
question that ordering exists to serve: in a year when the upstream town
discharged unusually badly, did the downstream town's intake look worse?

That is the pay-off of joining the archive to the river network, and it is also
the easiest place in the whole project to fool yourself. Two towns on one river
share weather, share a growing population, share the decade's industrial boom.
Their numbers will move together whether or not one is affecting the other, so a
correlation here is close to meaningless on its own.

What this module does, therefore, is smaller than it sounds and deliberately so:

* it reports the overlap honestly, including how few years it usually is;
* it computes a rank correlation rather than a linear one, because six points
  from OCR'd prose do not support anything finer;
* it states the confounders in the result rather than in a docstring nobody
  reads;
* it never uses the word "caused", and refuses to report anything at all below a
  minimum overlap.

A real attribution study needs travel time, dilution by river flow between the
two points, and every other discharger in between. None of that is here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from .models import Record
from .science import series_from_records

#: Below this many shared years, nothing is reported. Four points can be made to
#: correlate at r=1.0 by accident often enough that quoting one would be
#: misleading however it is hedged.
MIN_OVERLAP = 5


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Rank correlation. Robust to the outliers OCR produces, and makes no
    assumption that the relationship is linear -- neither of which a Pearson
    coefficient on six scanned readings could survive."""
    n = len(xs)
    if n < 3 or n != len(ys):
        return None

    def rank(values: Sequence[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                out[order[k]] = avg
            i = j + 1
        return out

    rx, ry = rank(xs), rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else None


@dataclass
class Influence:
    upstream: str
    downstream: str
    watercourse: str
    parameter: str
    years: list[int] = field(default_factory=list)
    upstream_values: list[float] = field(default_factory=list)
    downstream_values: list[float] = field(default_factory=list)
    correlation: float | None = None
    reportable: bool = False
    reason: str = ""
    confounders: list[str] = field(default_factory=list)

    def describe(self) -> str:
        if not self.reportable:
            return (
                f"{self.upstream} -> {self.downstream} ({self.parameter}): "
                f"not reportable — {self.reason}"
            )
        direction = (
            "move together" if (self.correlation or 0) > 0 else "move oppositely"
        )
        return (
            f"{self.upstream} effluent vs {self.downstream} influent "
            f"({self.parameter}, {len(self.years)} shared years): "
            f"rank correlation {self.correlation:+.2f} — they {direction}. "
            "This is association in a very short series, not evidence of effect."
        )


def upstream_influence(
    upstream_records: Sequence[Record],
    downstream_records: Sequence[Record],
    *,
    upstream_place: str,
    downstream_place: str,
    watercourse: str = "",
    parameter: str = "BOD",
    min_overlap: int = MIN_OVERLAP,
) -> Influence:
    """Compare an upstream town's effluent with a downstream town's influent.

    The pairing is deliberate: effluent is what the upper town put in the river,
    influent is what arrived at the lower town's plant. Comparing two effluents
    would only show that both towns were growing.
    """
    up = series_from_records(upstream_records, parameter=parameter, stream="effluent")
    down = series_from_records(downstream_records, parameter=parameter, stream="influent")

    up_by_year = {int(y): v for y, v, _ in up.points}
    down_by_year = {int(y): v for y, v, _ in down.points}
    shared = sorted(set(up_by_year) & set(down_by_year))

    result = Influence(
        upstream=upstream_place,
        downstream=downstream_place,
        watercourse=watercourse,
        parameter=parameter,
        years=shared,
        upstream_values=[up_by_year[y] for y in shared],
        downstream_values=[down_by_year[y] for y in shared],
        confounders=[
            "both towns share weather, and rainfall drives treatment plant loading",
            "both towns were growing through this period",
            "other dischargers between the two are not accounted for",
            "no travel time or dilution by river flow is modelled",
        ],
    )

    if len(shared) < min_overlap:
        result.reason = (
            f"only {len(shared)} shared years; {min_overlap} is the minimum, because "
            "a handful of points correlate by accident often enough that quoting a "
            "number would mislead however it is hedged"
        )
        return result

    result.correlation = spearman(result.upstream_values, result.downstream_values)
    if result.correlation is None:
        result.reason = "correlation undefined (no variance in one series)"
        return result

    result.reportable = True
    return result
