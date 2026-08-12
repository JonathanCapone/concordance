"""The edge of what this archive can currently answer.

A question the archive could answer has prerequisites -- specific documents that
have to be read before it becomes answerable at all. "Did what Fergus discharged
show up in Brantford's intake?" needs Fergus AND Brantford. Read one and the
question is not half-answered; it is still unanswerable, but it is now one
document away.

That gives the corpus an ordering nobody otherwise has. Eleven million pages
cannot be read alphabetically or chronologically in any useful sense, and reading
by subject only serves whoever picked the subject. Reading by *what it unlocks*
serves everyone, because a question one document away is a question that
somebody, somewhere, already wanted.

It also replaces badges with something true. "You have processed 40 documents" is
a number about you. "You made the Grand River comparison possible for everyone,
and it had been waiting on one town since 1961" is a fact about the world, and it
is the sort of thing that is worth an hour of somebody's electricity.

Three properties this deliberately has:

* **Questions are concrete.** Not "more data about water" but a named comparison
  between two named places over a named span.
* **Distance is honest.** A question needing four unread documents says four. It
  does not get rounded down to make the frontier look close.
* **Value compounds.** One document often sits on several questions at once, and
  the ranking says so, because that is exactly the document to read next.
"""

from __future__ import annotations

import collections
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .parameters import resolve as resolve_parameter

#: A trend needs this many years before it is worth computing. Matches the
#: minimum in science.trend() -- a frontier that promises a trend the statistics
#: layer will then refuse to produce would be lying.
MIN_TREND_YEARS = 6


@dataclass
class Question:
    """Something the archive could answer, and what it is waiting on."""

    kind: str
    text: str
    needs: list[str] = field(default_factory=list)          # places still unread
    have: list[str] = field(default_factory=list)           # places already read
    detail: str = ""
    value: float = 1.0                                      # how much it is worth

    @property
    def distance(self) -> int:
        return len(self.needs)

    @property
    def answerable(self) -> bool:
        return not self.needs

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "question": self.text,
            "answerable": self.answerable, "distance": self.distance,
            "waiting_on": self.needs, "already_read": self.have,
            "detail": self.detail, "value": round(self.value, 2),
        }


@dataclass
class Frontier:
    questions: list[Question] = field(default_factory=list)
    read_places: set[str] = field(default_factory=set)

    @property
    def answerable(self) -> list[Question]:
        return [q for q in self.questions if q.answerable]

    @property
    def waiting(self) -> list[Question]:
        return sorted((q for q in self.questions if not q.answerable),
                      key=lambda q: (q.distance, -q.value))

    def unlocks(self, place: str) -> list[Question]:
        """Questions that reading this one place would make answerable.

        The honest version of a progress bar: what your hour actually buys, said
        before you spend it.
        """
        key = place.strip().lower()
        return [q for q in self.questions
                if q.distance == 1 and q.needs[0].strip().lower() == key]

    def ranked_places(self, limit: int = 20) -> list[dict[str, Any]]:
        """Unread places, ordered by how much reading them would open up.

        A place appearing in several near-answerable questions ranks above one
        that appears in a single distant one -- which is the whole reason to
        compute this rather than read alphabetically.
        """
        score: collections.Counter = collections.Counter()
        detail: dict[str, list[str]] = collections.defaultdict(list)
        for q in self.questions:
            if q.answerable or not q.needs:
                continue
            # A question one document away is worth far more than one four away:
            # finishing something beats inching toward it.
            share = q.value / (q.distance ** 2)
            for place in q.needs:
                score[place] += share
                if q.distance <= 2:
                    detail[place].append(q.text)
        out = []
        for place, points in score.most_common(limit):
            out.append({
                "place": place,
                "score": round(points, 2),
                "unlocks_now": len(self.unlocks(place)),
                "questions": detail[place][:4],
            })
        return out


# --------------------------------------------------------------------------
# building the frontier
# --------------------------------------------------------------------------

def _years_for(records: Iterable[dict[str, Any]], place: str) -> set[int]:
    out = set()
    for r in records:
        if str(r.get("place") or "").strip().lower() != place.strip().lower():
            continue
        period = str(r.get("period") or "")[:4]
        if period.isdigit():
            out.add(int(period))
    return out


def build(
    records: list[dict[str, Any]],
    *,
    downstream_links: list[Any] | None = None,
    coverage: dict[str, list[int]] | None = None,
) -> Frontier:
    """Work out what is answerable, what is close, and what each place unlocks.

    `coverage` is every place the archive HOLDS documents for and the years they
    cover -- the silence report. `records` is what has actually been READ. The
    gap between those two is the frontier.
    """
    read_places = {str(r.get("place") or "").strip() for r in records if r.get("place")}
    read_lower = {p.lower() for p in read_places if p}
    coverage = coverage or {}
    frontier = Frontier(read_places=read_places)

    # -- 1. downstream comparisons -----------------------------------------
    # The most valuable kind: needs two specific places and answers something
    # nobody can currently ask at all.
    for link in downstream_links or []:
        up, down = link.upstream, link.downstream
        needs = [p for p in (up, down) if p.lower() not in read_lower]
        have = [p for p in (up, down) if p.lower() in read_lower]
        frontier.questions.append(Question(
            kind="downstream",
            text=f"Did what {up} discharged show up in {down}'s intake?",
            needs=needs, have=have,
            detail=f"on the {link.watercourse}",
            # Worth more than a single-place question: it is a relationship, and
            # relationships are the thing a single report can never contain.
            value=3.0,
        ))

    # -- 2. trends ----------------------------------------------------------
    for place, years in coverage.items():
        if len(years) < MIN_TREND_YEARS:
            continue
        if place.lower() in read_lower:
            got = _years_for(records, place)
            if len(got) >= MIN_TREND_YEARS:
                frontier.questions.append(Question(
                    kind="trend",
                    text=f"Did treatment at {place} improve between "
                         f"{min(years)} and {max(years)}?",
                    needs=[], have=[place],
                    detail=f"{len(got)} years read", value=2.0,
                ))
                continue
        frontier.questions.append(Question(
            kind="trend",
            text=f"Did treatment at {place} improve between {min(years)} and {max(years)}?",
            needs=[place], have=[],
            detail=f"{len(years)} surviving reports, enough for a trend", value=2.0,
        ))

    # -- 3. the shape of a whole river -------------------------------------
    by_river: dict[str, set[str]] = collections.defaultdict(set)
    for link in downstream_links or []:
        by_river[link.watercourse].update({link.upstream, link.downstream})
    for river, towns in by_river.items():
        if len(towns) < 3:
            continue
        needs = sorted(t for t in towns if t.lower() not in read_lower)
        frontier.questions.append(Question(
            kind="river",
            text=f"What did the {river} carry, end to end, in a single year?",
            needs=needs, have=sorted(t for t in towns if t.lower() in read_lower),
            detail=f"{len(towns)} towns along it",
            # Whole-river pictures are the most valuable and the hardest to
            # finish, which is exactly why they need naming rather than hoping.
            value=5.0,
        ))

    # -- 4. the silence, checked against readings --------------------------
    for place, years in coverage.items():
        if not years:
            continue
        if max(years) >= 1975:
            continue
        if place.lower() in read_lower:
            continue
        frontier.questions.append(Question(
            kind="silence",
            text=f"What was {place} discharging when the record stops in {max(years)}?",
            needs=[place], have=[],
            detail="the last thing anyone recorded before it went quiet",
            value=1.5,
        ))

    return frontier


def load(
    results_dir: str | Path = "data/results",
    silence_report: str | Path = "data/results/silence_report.json",
    downstream_links: list[Any] | None = None,
) -> Frontier:
    """Build the frontier from whatever is on disk."""
    skip = {"gold_report", "metadata_proposals", "silence_report", "corpus_census",
            "audit", "cost_model", "vocab_proposals", "frontier"}
    records: list[dict[str, Any]] = []
    for path in Path(results_dir).glob("*.json"):
        if path.stem in skip:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        records.extend(payload.get("records") or [])

    coverage: dict[str, list[int]] = {}
    p = Path(silence_report)
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        coverage = {m["place"]: m["reported_years"] for m in data.get("municipalities", [])}

    return build(records, downstream_links=downstream_links, coverage=coverage)
