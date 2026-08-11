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
    u = re.sub(r"\s+", " ", u)
    if u in UNIT_ALIASES:
        return UNIT_ALIASES[u]
    u2 = u.replace(" per ", "/")
    return UNIT_ALIASES.get(u2, u)


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
        gv, gu = g.get("value"), norm_unit(g.get("unit"))
        hit = None
        # Prefer a candidate that also agrees on kind, so that when a page
        # states the same number as both design and observation we pair them up
        # correctly rather than by accident of ordering.
        for want_kind in (True, False):
            for r in remaining:
                if want_kind and r.kind != g.get("kind"):
                    continue
                if values_match(gv, r.value) and norm_unit(r.unit) == gu:
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
        return {
            "matched": m,
            "missed": miss,
            "spurious": spur,
            "recall": round(recall, 4),
            "precision": round(precision, 4),
            "f1": round(f1, 4),
            "kind_accuracy": round(kind_ok / m, 4) if m else 1.0,
            "stream_accuracy": round(self._agg("stream_accuracy"), 4),
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
            f"  stream accuracy  {t['stream_accuracy']:.1%}   (influent vs effluent)",
        ]
        confusions = [c for s in self.scores for c in s.kind_confusions()]
        if confusions:
            lines += ["", "  kind confusions (the dangerous errors):"]
            for want, got, val, param in confusions:
                lines.append(f"    {val} {param[:28]:<28} gold={want:<12} got={got}")
        return "\n".join(lines)


def load_gold(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
