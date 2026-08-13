"""The accuracy harness.

This is the gate. If extraction is not measurably good, the honest move is to
narrow scope and say so publicly -- not to ship a confident-looking dataset of
numbers nobody has checked. An archive that has been misread at scale is worse
than one that has not been read at all, because the errors look like findings.

What is measured, and why each one separately:

* **value recall / precision** -- did we recover the numbers that are there,
  without inventing ones that aren't.
* **kind accuracy** -- among matched values, did we correctly tell an
  observation from a design specification from a regulatory standard. This is
  reported apart from value accuracy because a perfectly-read number filed under
  the wrong kind is not a small error: a design capacity charted as a
  measurement produces a clean, plausible, entirely fictional trend.
* **stream accuracy** -- influent vs effluent. Getting this backwards turns a
  working treatment plant into a polluting one.

Units are compared after normalisation, since 1960s OCR renders "mg/L" as
"mg/1" and reports vary between "mgd" and "million gallons per day".
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import Record

#: Unit spellings seen in the corpus, mapped to a canonical form.
UNIT_ALIASES = {
    "mg/1": "mg/l", "mg/l": "mg/l", "mgl": "mg/l", "milligrams per litre": "mg/l",
    "milligrams per liter": "mg/l", "ppm": "mg/l",
    "%": "%", "percent": "%", "per cent": "%", "pct": "%",
    "mgd": "mgd", "million gallons per day": "mgd", "mg/d": "mgd",
    "million gallons": "million gallons", "mil gal": "million gallons",
    "cu ft": "cu ft", "cu. ft.": "cu ft", "cubic feet": "cu ft", "ft3": "cu ft",
    "gallons": "gallons", "gal": "gallons",
    "gallons per minute": "gpm", "gpm": "gpm",
    "$": "$", "dollars": "$", "cad": "$",
    "people": "people", "persons": "people", "population": "people",
    "ug/m3": "ug/m3", "µg/m3": "ug/m3", "ug/m": "ug/m3",
}


def norm_unit(unit: str | None) -> str:
    """Canonical form of a unit as written in a 1960s report.

    Periods are removed entirely rather than merely trimmed from the ends:
    the corpus writes cubic feet as "cu. ft.", and stripping only the outer dot
    leaves "cu. ft", which matches nothing. That silently dropped every grit
    measurement in the Owen Sound gold set before a test caught it.
    """
    if not unit:
        return ""
    u = re.sub(r"\s+", " ", str(unit).replace(".", " ").strip().lower())
    # Whitespace around a solidus carries no meaning. The gold set writes
    # "gal/ft2/day" and the model returned "gal/ft2 /day" for the same reading,
    # and the two failed to match -- a correct extraction scored as both a miss
    # and a fabrication, costing twice.
    u = re.sub(r"\s*/\s*", "/", u)
    u = re.sub(r"\s+", " ", u)
    # "^" is how a model writes a superscript the page prints: the gold set has
    # "gal/ft2/day" and the extractor returned "gal/ft^2/day" for the same
    # reading.
    u = u.replace("^", "")
    if u in UNIT_ALIASES:
        return UNIT_ALIASES[u]

    # Fall back to the SOLIDUS form, not the original. "$ per million gallons"
    # and "$/million gallons" are one unit written two ways, and returning the
    # unnormalised string left them different -- so eight correct readings on
    # the Owen Sound pages scored as both a miss and a fabrication, costing
    # twice each and dropping precision about five points.
    #
    # This does not merge "pounds" with "pounds per month": those become
    # "pounds" and "pounds/month", which is the distinction worth keeping. The
    # rate implied by a PARAMETER name is reconciled separately, in
    # canonical_quantity, and that reconciliation was silently useless while
    # this function returned the spelled-out form.
    u2 = u.replace(" per ", "/")
    return UNIT_ALIASES.get(u2, u2)


def values_match(a: float | None, b: float | None, *, rel: float = 0.01) -> bool:
    """Equal within 1% relative, which absorbs OCR spacing artefacts.

    "8. 8 million gallons" is 8.8; a reader that returns 8.8 is correct and one
    that returns 88 is not, and 1% separates those cleanly.
    """
    if a is None or b is None:
        return a is None and b is None
    if a == b:
        return True
    scale = max(abs(a), abs(b))
    return scale > 0 and abs(a - b) / scale <= rel


#: Multiplier to a base unit, so a quantity written at different scales compares
#: equal. "3.0 million gallons" and "3000000 gallons" are the same measurement,
#: and scoring them as a miss AND a false positive double-punishes a correct read.
_SCALE: dict[str, tuple[str, float]] = {
    "million gallons": ("gallons", 1e6),
    "mil gal": ("gallons", 1e6),
    "thousand gallons": ("gallons", 1e3),
    "gallons": ("gallons", 1.0),
    "mgd": ("gallons/day", 1e6),
    "gallons/day": ("gallons/day", 1.0),
    "million gallons/day": ("gallons/day", 1e6),
}

#: Rate suffixes a reader may legitimately place in the PARAMETER NAME rather
#: than the unit -- "average daily flow" in million gallons is the same claim as
#: "flow" in million gallons per day. Reconciled rather than counted wrong.
_RATE_WORDS: dict[str, str] = {
    "daily": "day", "per day": "day", "/day": "day",
    "monthly": "month", "per month": "month", "/month": "month",
    "annual": "year", "yearly": "year", "per year": "year", "/year": "year",
    "hourly": "hour", "per hour": "hour",
}


def canonical_quantity(
    value: float | None, unit: str | None, parameter: str = ""
) -> tuple[float | None, str]:
    """Reduce (value, unit, parameter) to a comparable (magnitude, base unit).

    Folds scale prefixes into the number, and moves any rate implied by the
    parameter name into the unit, so that two correct readings written
    differently compare equal.
    """
    u = norm_unit(unit)
    if value is None:
        return None, u

    base, mult = _SCALE.get(u, (u, 1.0))
    val = value * mult

    # If the unit carries no rate but the parameter name implies one, adopt it.
    if "/" not in base:
        p = parameter.lower()
        for word, period in _RATE_WORDS.items():
            if word in p:
                base = f"{base}/{period}"
                break
    return val, base


def quantities_match(
    gold: dict[str, Any], got: Any, *, rel: float = 0.01
) -> bool:
    """True when two readings describe the same physical quantity."""
    gv, gu = canonical_quantity(
        gold.get("value"), gold.get("unit"), str(gold.get("parameter", ""))
    )
    rv, ru = canonical_quantity(got.value, got.unit, got.parameter or "")
    return gu == ru and values_match(gv, rv, rel=rel)


@dataclass
class Match:
    gold: dict[str, Any]
    got: Record


@dataclass
class PageScore:
    page: int
    matches: list[Match] = field(default_factory=list)
    missed: list[dict[str, Any]] = field(default_factory=list)      # in gold, not found
    spurious: list[Record] = field(default_factory=list)            # found, not in gold

    @property
    def recall(self) -> float:
        total = len(self.matches) + len(self.missed)
        return len(self.matches) / total if total else 1.0

    @property
    def precision(self) -> float:
        total = len(self.matches) + len(self.spurious)
        return len(self.matches) / total if total else 1.0

    @property
    def kind_accuracy(self) -> float:
        if not self.matches:
            return 1.0
        ok = sum(1 for m in self.matches if m.gold.get("kind") == m.got.kind)
        return ok / len(self.matches)

    @property
    def stream_accuracy(self) -> float:
        """Only scored where gold actually specifies a stream."""
        rel = [m for m in self.matches if m.gold.get("stream")]
        if not rel:
            return 1.0
        ok = sum(1 for m in rel if m.gold.get("stream") == m.got.stream)
        return ok / len(rel)

    def kind_confusions(self) -> list[tuple[str, str, float | None, str]]:
        return [
            (str(m.gold.get("kind")), m.got.kind, m.got.value, m.got.parameter)
            for m in self.matches
            if m.gold.get("kind") != m.got.kind
        ]


def score_page(gold_entries: list[dict[str, Any]], got: list[Record], page: int) -> PageScore:
    """Greedy match on (value, normalised unit). Values are distinctive enough
    to anchor on, which avoids penalising harmless differences in how a
    parameter is named ("influent BOD" vs "BOD" + stream=influent).
    """
    result = PageScore(page=page)
    remaining = list(got)

    for g in gold_entries:
        hit = None
        # Prefer a candidate that also agrees on kind, so that when a page
        # states the same number as both design and observation we pair them up
        # correctly rather than by accident of ordering.
        for want_kind in (True, False):
            for r in remaining:
                if want_kind and r.kind != g.get("kind"):
                    continue
                if quantities_match(g, r):
                    hit = r
                    break
            if hit:
                break
        if hit:
            remaining.remove(hit)
            result.matches.append(Match(gold=g, got=hit))
        else:
            result.missed.append(g)

    result.spurious = remaining
    return result


@dataclass
class Report:
    scores: list[PageScore]

    def _agg(self, attr: str) -> float:
        vals = [getattr(s, attr) for s in self.scores]
        return sum(vals) / len(vals) if vals else 0.0

    @property
    def totals(self) -> dict[str, Any]:
        m = sum(len(s.matches) for s in self.scores)
        miss = sum(len(s.missed) for s in self.scores)
        spur = sum(len(s.spurious) for s in self.scores)
        recall = m / (m + miss) if (m + miss) else 1.0
        precision = m / (m + spur) if (m + spur) else 1.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        kind_ok = sum(
            1 for s in self.scores for x in s.matches if x.gold.get("kind") == x.got.kind
        )
        stream_pairs = [x for s in self.scores for x in s.matches if x.gold.get("stream")]
        stream_n = len(stream_pairs)
        stream_ok = sum(1 for x in stream_pairs if x.gold.get("stream") == x.got.stream)
        return {
            "matched": m,
            "missed": miss,
            "spurious": spur,
            "recall": round(recall, 4),
            "precision": round(precision, 4),
            "f1": round(f1, 4),
            "kind_accuracy": round(kind_ok / m, 4) if m else 1.0,
            # Micro-averaged over every stream-bearing pair, not the mean of
            # per-page rates. PageScore.stream_accuracy returns 1.0 when a page
            # has nothing to judge, which is right for a page and wrong for a
            # total: adding a gold page that the extractor missed entirely
            # raised the published figure from 86.7% to 90.0%, because a page
            # with no matches contributed a perfect score.
            #
            # A control that improves when the thing it measures fails is not a
            # control. This project has now built four of those.
            "stream_accuracy": round(stream_ok / stream_n, 4) if stream_n else None,
            "stream_pairs_judged": stream_n,
        }

    def render(self) -> str:
        t = self.totals
        lines = [
            "accuracy vs hand-checked ground truth",
            "-" * 52,
            f"  matched          {t['matched']}",
            f"  missed           {t['missed']}   (in gold, not extracted)",
            f"  spurious         {t['spurious']}   (extracted, not in gold)",
            "",
            f"  recall           {t['recall']:.1%}",
            f"  precision        {t['precision']:.1%}",
            f"  f1               {t['f1']:.1%}",
            "",
            f"  kind accuracy    {t['kind_accuracy']:.1%}   (observation vs design vs standard)",
            (f"  stream accuracy  {t['stream_accuracy']:.1%}   "
             f"(influent vs effluent, {t['stream_pairs_judged']} pairs judged)"
             if t["stream_accuracy"] is not None
             else "  stream accuracy  not judged -- no matched pair carried a stream"),
        ]
        confusions = [c for s in self.scores for c in s.kind_confusions()]
        if confusions:
            lines += ["", "  kind confusions (the dangerous errors):"]
            for want, got, val, param in confusions:
                lines.append(f"    {val} {param[:28]:<28} gold={want:<12} got={got}")
        return "\n".join(lines)


def load_gold(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
