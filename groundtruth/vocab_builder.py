"""Propose vocabulary from what the archive actually says.

The vocabulary decides what a number means, and that is a judgement -- it should
not be automated away. But nobody should have to author it from a blank page
either, when the documents are right there saying what they measure.

So: the machine harvests every parameter name the extractor produced that the
table does not recognise, clusters obvious synonyms, and ranks by how often each
occurs. A person then confirms, corrects or rejects. They are editing a sorted
list of real terms rather than inventing a controlled vocabulary from memory,
and every proposal carries an example sentence from a real page so the decision
is made with the evidence in view.

This is deliberately NOT a model deciding what things mean. Clustering
"suspended solids" with "suspended solids concentration" is string work.
Deciding that "BOD removal" and "BOD exceedance frequency" are different
measurements -- one an efficiency, one a count of failures, both percentages --
is the judgement that got this project wrong once already, and no amount of
compute substitutes for it.
"""

from __future__ import annotations

import collections
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .parameters import resolve as resolve_parameter

_NOISE = re.compile(r"^\W*$|^\d+$")


def _stem(name: str) -> str:
    """Crude normalisation for grouping. Not linguistics -- just enough to put
    'suspended solids' and 'Suspended Solids Concentration' in one bucket."""
    t = re.sub(r"[^a-z0-9 ]+", " ", str(name).lower())
    t = re.sub(r"\b(average|total|annual|daily|monthly|mean|maximum|minimum|"
               r"concentration|content|level|value|reading|rate)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


@dataclass
class Proposal:
    """One suggested vocabulary entry, for a person to accept or reject."""

    stem: str
    count: int
    variants: list[str] = field(default_factory=list)
    units: list[tuple[str, int]] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)
    suggested_domain: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposed_term": self.stem,
            "occurrences": self.count,
            "written_as": self.variants[:8],
            "units_seen": self.units[:6],
            "suggested_domain": self.suggested_domain,
            "examples": self.examples[:3],
            "decision": None,          # a person fills this in
            "canonical": None,         # ...and this
        }


#: Rough domain hints from units and wording. A suggestion only -- the point is
#: to save a human sorting, not to decide for them.
_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"mg/|ug/|ppm|ppb|coliform|turbid|chlorin", re.I), "water"),
    (re.compile(r"pupil|school|exam|grade|enrol|teacher|curricul", re.I), "education"),
    (re.compile(r"acre|crop|yield|livestock|farm|fertil", re.I), "agriculture"),
    (re.compile(r"timber|forest|silvicult|stand|cord", re.I), "forestry"),
    (re.compile(r"census|dwelling|household|populat", re.I), "population"),
    (re.compile(r"gas|petroleum|coal|kwh|megawatt|barrel", re.I), "energy"),
    (re.compile(r"ore|tonnage|mine|smelt", re.I), "mining"),
    (re.compile(r"emission|stack|ambient|dustfall|smoke", re.I), "air"),
]


def _hint(text: str) -> str | None:
    for pattern, domain in _HINTS:
        if pattern.search(text):
            return domain
    return None


def harvest(
    records: Iterable[dict[str, Any]],
    *,
    min_count: int = 2,
    limit: int = 200,
) -> list[Proposal]:
    """Group unrecognised parameter names into candidate vocabulary entries.

    `min_count` exists because a term appearing once is usually an OCR accident
    or a one-off phrasing, and a list padded with those is a list nobody reads.
    """
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)

    for record in records:
        name = str(record.get("parameter") or "").strip()
        if not name or _NOISE.match(name):
            continue
        if resolve_parameter(name, record.get("unit")) is not None:
            continue          # already known
        stem = _stem(name)
        if stem:
            groups[stem].append(record)

    proposals: list[Proposal] = []
    for stem, rows in groups.items():
        if len(rows) < min_count:
            continue
        units = collections.Counter(str(r.get("unit") or "").strip() for r in rows if r.get("unit"))
        variants = collections.Counter(str(r.get("parameter")).strip() for r in rows)
        examples = []
        for r in rows[:3]:
            prov = r.get("provenance") or {}
            examples.append({
                "value": r.get("value"), "unit": r.get("unit"),
                "read_from": (prov.get("source_text") or "")[:140],
                "page_url": prov.get("page_url") or "",
            })
        proposals.append(Proposal(
            stem=stem,
            count=len(rows),
            variants=[v for v, _ in variants.most_common()],
            units=units.most_common(),
            examples=examples,
            suggested_domain=_hint(stem + " " + " ".join(units)),
        ))

    proposals.sort(key=lambda p: -p.count)
    return proposals[:limit]


def harvest_results(directory: str | Path = "data/results", **kwargs: Any) -> list[Proposal]:
    """Harvest from every extraction file on disk."""
    skip = {"gold_report", "metadata_proposals", "silence_report", "corpus_census",
            "audit", "cost_model", "vocab_proposals"}
    records: list[dict[str, Any]] = []
    for path in Path(directory).glob("*.json"):
        if path.stem in skip:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        records.extend(payload.get("records") or [])
    return harvest(records, **kwargs)


def to_review_file(proposals: list[Proposal], path: str | Path) -> dict[str, Any]:
    """Write proposals as a file a person edits and hands back.

    Deliberately a plain JSON file rather than a database or a web form: it can
    be reviewed offline, diffed, argued about in a pull request, and it does not
    require running anything.
    """
    payload = {
        "how_to_use": (
            "For each entry set 'decision' to keep or drop, and 'canonical' to the "
            "name this measurement should have. Entries you leave alone are "
            "ignored. Terms are grouped by a crude stem, so check 'written_as' -- "
            "if two genuinely different measurements have been grouped together, "
            "split them rather than picking one."
        ),
        "warning": (
            "Grouping is string work and is done for you. Deciding what a "
            "measurement MEANS is not, and is the thing this project has got "
            "wrong before: 'BOD removal' and 'BOD exceedance frequency' are both "
            "percentages of BOD and are opposite in meaning."
        ),
        "n_proposals": len(proposals),
        "proposals": [p.to_dict() for p in proposals],
    }
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def apply_review(path: str | Path) -> dict[str, list[tuple[str, str]]]:
    """Turn a reviewed file into VOCABULARY blocks ready to paste in.

    Only entries a person explicitly marked 'keep' are emitted. Silence is not
    consent: an unreviewed proposal stays out of the vocabulary.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    for entry in payload.get("proposals", []):
        if entry.get("decision") != "keep":
            continue
        canonical = entry.get("canonical") or entry.get("proposed_term")
        domain = entry.get("suggested_domain") or "unsorted"
        for variant in entry.get("written_as", []):
            out[domain].append((variant.lower(), canonical))
        out[domain].append((entry["proposed_term"], canonical))
    return {k: sorted(set(v), key=lambda p: -len(p[0])) for k, v in out.items()}
