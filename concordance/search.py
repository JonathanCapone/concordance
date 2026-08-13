"""Find the documents you care about, offline.

The whole 104,241-item index sits on disk after one download: titles, years,
subjects, publishers, page counts. So searching it is a dictionary scan, not a
network call, and someone deciding what to read can browse the entire collection
in milliseconds without an account, an API key, or a connection.

That matters for the contribution model. A person interested in Ontario
schooling should be able to find the 4,147 items about it, see how much reading
they represent, and start — without asking anyone's permission or waiting on a
server.
"""

from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from .archive import Archive
from .parameters import facility_of

#: Words too common in this collection to narrow anything.
_STOP = {
    "the", "of", "and", "for", "in", "on", "a", "an", "to", "report", "annual",
    "ontario", "canada", "canadian", "government", "ministry", "department",
}


def _tokens(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", str(text).lower()) if len(w) > 1]


@dataclass
class Hit:
    identifier: str
    title: str
    year: int | None
    publisher: str
    subjects: list[str]
    pages: int | None
    facility: str | None
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "identifier": self.identifier, "title": self.title, "year": self.year,
            "publisher": self.publisher, "subjects": self.subjects[:6],
            "pages": self.pages, "facility": self.facility,
            "url": f"https://archive.org/details/{self.identifier}",
        }


@dataclass
class Results:
    query: str
    hits: list[Hit] = field(default_factory=list)
    total: int = 0
    years: dict[int, int] = field(default_factory=dict)
    publishers: list[tuple[str, int]] = field(default_factory=list)
    subjects: list[tuple[str, int]] = field(default_factory=list)

    @property
    def estimated_pages(self) -> int:
        known = [h.pages for h in self.hits if h.pages]
        if not known:
            return 0
        mean = sum(known) / len(known)
        return int(mean * self.total)

    def effort(self, seconds_per_page: float = 150.0, worth_reading: float = 0.531) -> dict:
        """What reading this selection would actually cost.

        Shown before anyone starts, because "4,147 items about education" and
        "eleven months of continuous inference" are the same fact and only one of
        them is actionable.
        """
        pages = self.estimated_pages
        readable = pages * worth_reading
        hours = readable * seconds_per_page / 3600
        return {
            "documents": self.total,
            "estimated_pages": pages,
            "pages_worth_reading": int(readable),
            "hours": round(hours, 1),
            "days": round(hours / 24, 1),
            "note": (
                "Estimated from the corpus census: 69.5% of pages carry "
                "measurements, and this machine reads one in about 91 seconds. "
                "Split the work and divide the time."
            ),
        }


def search(
    index: Iterable[dict[str, Any]],
    query: str = "",
    *,
    year_range: tuple[int, int] | None = None,
    publisher: str | None = None,
    limit: int = 40,
    min_score: float = 2.0,
) -> Results:
    """Rank items by how well title and subjects match the query.

    Scoring is deliberately simple -- term frequency with a bonus for title and
    subject hits. A cleverer ranker would be easy and would also be a thing to
    maintain; the corpus is small enough that a person can just read the list.
    """
    terms = [t for t in _tokens(query) if t not in _STOP]
    out: list[Hit] = []
    years: collections.Counter = collections.Counter()
    pubs: collections.Counter = collections.Counter()
    subs: collections.Counter = collections.Counter()

    for item in index:
        title = str(item.get("title") or "")
        raw_subj = item.get("subject") or []
        subjects = [str(s) for s in (raw_subj if isinstance(raw_subj, list) else [raw_subj])]
        raw_pub = item.get("publisher") or []
        pub = str((raw_pub[0] if isinstance(raw_pub, list) and raw_pub else raw_pub) or "")

        try:
            year = int(str(item.get("year"))[:4])
        except (TypeError, ValueError):
            year = None

        if year_range and (year is None or not year_range[0] <= year <= year_range[1]):
            continue
        if publisher and publisher.lower() not in pub.lower():
            continue

        score = 0.0
        if terms:
            hay_title = title.lower()
            hay_subj = " ".join(subjects).lower()
            for t in terms:
                if t in hay_title:
                    score += 3.0
                if t in hay_subj:
                    score += 2.0
                if t in pub.lower():
                    score += 0.5
            # A publisher-only match is not a match. Searching "education" once
            # returned 6,597 documents, of which 1,302 scored 0.5 -- they were
            # about anything at all and merely happened to be published by a
            # Department of Education. Counting those inflated the headline and
            # every effort estimate built on it.
            if score < min_score:
                continue
        else:
            score = 1.0

        try:
            pages = int(item.get("imagecount"))
        except (TypeError, ValueError):
            pages = None

        out.append(Hit(
            identifier=item.get("identifier", ""), title=title, year=year,
            publisher=pub, subjects=subjects, pages=pages,
            facility=facility_of(title), score=score,
        ))
        if year:
            years[year] += 1
        if pub:
            pubs[pub[:60]] += 1
        for s in subjects[:4]:
            subs[s[:50]] += 1

    out.sort(key=lambda h: (-h.score, h.year or 9999))
    return Results(
        query=query, hits=out[:limit], total=len(out),
        years=dict(sorted(years.items())),
        publishers=pubs.most_common(8),
        subjects=subs.most_common(12),
    )


def search_archive(query: str = "", **kwargs: Any) -> Results:
    """Convenience wrapper over the cached index."""
    return search(Archive().load_index(), query, **kwargs)
