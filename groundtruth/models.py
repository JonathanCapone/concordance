"""The data model.

The archive is a sensor network that ran for 150 years. Every civil servant who
wrote a measurement down was a node. This module defines what one of their
readings looks like once it has been read back out of the paper.

Four kinds of record, and keeping them apart is load-bearing:

  observation  what someone actually measured, here, then
  standard     what the regulatory limit was *at that time*
  design       what the plant was *built* to handle -- a specification, not a reading
  conclusion   what the author claimed on the basis of the numbers

You cannot answer "was 104 mg/L bad?" without the standard *of that era*, which
is why standards are extracted as first-class records rather than discarded.

`design` exists because of a real trap found in the corpus. The Owen Sound 1969
report states "BOD - Raw Sewage 180 mg/1" on its design-data page and "average
influent BOD ... 104 mg/1" in its review. Both are BOD in mg/L for the same
plant in the same document. One is the capacity it was engineered for, the other
is what actually flowed through it. Conflating them would silently corrupt every
downstream trend.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Literal

RecordKind = Literal["observation", "standard", "design", "conclusion"]

#: How the value relates to the underlying series. A 1969 report rarely gives a
#: raw reading; it gives a summary of one, and the summary type matters.
Qualifier = Literal[
    "average", "mean", "median", "maximum", "minimum",
    "range_low", "range_high", "total", "count", "percent", "point",
]

#: Which side of a process the measurement was taken on. Sewage treatment
#: reports are almost always paired -- what went in, what came out -- and losing
#: that distinction turns a working plant into a polluting one.
Stream = Literal["influent", "effluent", "ambient", "raw", "treated", "unknown"]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


@dataclass(frozen=True)
class Provenance:
    """Where a number came from, precisely enough to go and look at it.

    Every record must be falsifiable by a human in under a minute: the page
    image is one URL away, and `source_text` is the exact sentence the value was
    read out of. No number in this system is ever unfalsifiable.
    """

    identifier: str               # Internet Archive item id
    page: int | None = None       # 1-indexed page within the item
    source_text: str = ""         # the sentence the value was read from
    extractor: str = ""           # which path+model produced it
    path: Literal["prose", "vision", "manual"] = "prose"

    @property
    def item_url(self) -> str:
        return f"https://archive.org/details/{self.identifier}"

    @property
    def page_url(self) -> str:
        """Deep link to the exact scanned page, so a claim can be checked."""
        if self.page is None:
            return self.item_url
        return f"https://archive.org/details/{self.identifier}/page/n{self.page - 1}/mode/2up"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["page_url"] = self.page_url
        return d


#: Parameters that name what they count, so a missing unit symbol is not a
#: defect. The archive is mostly counts -- people, schools, beds, farms, cases,
#: dwellings -- and in French as well as English, since a third of this corpus
#: is bilingual and Statistics Canada publishes both columns on one page.
#: Written with `(?<![a-z])` and `(?![a-z])` rather than `\b` on purpose. This
#: exact pattern was authored once through a shell heredoc, which turned every
#: `\b` into a literal backspace byte (0x08) -- the file read back correctly in
#: every editor and matched nothing at all, including "elementary schools"
#: against `schools?`. The project has been bitten by that before and the work
#: log says so; using no backslash-b at all removes the trap rather than
#: documenting it. There is a repo-wide control-byte check for the same reason.
_COUNTED_PARAMETER = re.compile(
    r"(?<![a-z])("
    r"population|persons?|people|men|women|males?|females?|children|"
    r"hommes|femmes|personnes|enfants|"
    r"pupils?|students?|teachers?|schools?|classrooms?|graduates?|enrol|"
    r"dwellings?|households?|families|logements?|m[eé]nages?|familles|"
    r"beds?|patients?|operations?|transplants?|physicians?|nurses?|lits|"
    r"farms?|cattle|swine|poultry|livestock|fermes?|"
    r"employees?|workers?|staff|members?|officers?|travailleurs?|"
    r"births?|deaths?|cases?|complaints?|appeals?|convictions?|"
    r"naissances|d[eé]c[eè]s|"
    r"vehicles?|accidents?|licen[cs]es?|permits?|claims?|"
    r"volumes?|units?|rooms?|buildings?|plants?|wells?|mines?|"
    r"counts?|numbers?|statuts?"
    r")(?![a-z])", re.I)


@dataclass
class Record:
    """One reading recovered from the paper.

    `confidence` is *reading* confidence, not instrument accuracy. It says how
    sure we are that the sentence meant what we think it meant -- a distinction
    OMEGA never had to make, because a sensor's error comes from a spec sheet
    and this one comes from a smudged 1969 scan. It has to propagate into every
    trend line downstream or a guess gets presented as a fact.
    """

    kind: RecordKind
    parameter: str                          # "BOD", "suspended solids", "sulphur dioxide"
    value: float | None = None
    unit: str | None = None
    qualifier: Qualifier | None = None
    stream: Stream = "unknown"

    place: str | None = None                # "Owen Sound"
    period: str | None = None               # "1969", "1980-06", "1978-04-23"

    #: Which facility in that place. One town commonly has several, and they
    #: measure opposite things: a water pollution control plant reports what the
    #: town DISCHARGED, a water supply system reports what residents DRANK.
    #: Owen Sound has both in this collection -- sewage annual reports through
    #: 1974 and Drinking Water Surveillance reports from 1990 -- and merging them
    #: under one place name would put effluent and tap water on the same chart.
    facility: str | None = None

    confidence: float = 0.0                 # 0..1, reading confidence
    provenance: Provenance | None = None

    #: Set by the methods-drift layer when this value is not safely comparable
    #: to others of the same parameter (unit change, redefined test, etc).
    comparability_note: str | None = None

    notes: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    # -- identity ---------------------------------------------------------

    @property
    def key(self) -> str:
        """Stable identity for dedup across re-runs and across both paths.

        Deliberately excludes confidence and extractor: the same sentence read
        twice by different models is the same reading, and should collapse.
        """
        parts = [
            self.kind,
            _slug(self.parameter),
            f"{self.value}",
            _slug(self.unit or ""),
            self.qualifier or "",
            self.stream,
            _slug(self.place or ""),
            _slug(self.facility or ""),
            self.period or "",
            self.provenance.identifier if self.provenance else "",
            str(self.provenance.page) if self.provenance and self.provenance.page else "",
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]

    # -- validation -------------------------------------------------------

    def problems(self) -> list[str]:
        """Why this record should not be trusted. Empty list means it passed.

        Kept as a list rather than a bool so the QC layer can report *what* was
        wrong, and so a marginal record can be surfaced rather than silently
        dropped -- silently dropping data is how archives lose things twice.
        """
        out: list[str] = []
        if not self.parameter.strip():
            out.append("empty parameter")
        if self.kind in ("observation", "standard", "design"):
            if self.value is None:
                out.append("no value")
            # A missing unit is a defect only where a unit was ever going to
            # exist. Most of this archive counts things, and the unit is the
            # noun: "1,825 men", "75 elementary schools", "430 beds". Requiring
            # a symbol threw away every record on a Statistics Canada census
            # page -- 25 of 25 -- because a count of men has no mg/L to give.
            #
            # And on a table page it is not a defect at all. The unit lives in
            # the caption or the column head, which the model may not have been
            # given and the OCR may have destroyed, while the cell itself stays
            # perfectly checkable: its headings are on the page and its value is
            # in the page's digits. Demanding a symbol there discarded 20 of 29
            # records from a census table of the labour force -- counts of
            # people, correct, and rejected for having no mg/L.
            #
            # Extending the counted-noun list every time a new domain appears is
            # the wrong repair. The list is a vocabulary, vocabularies are never
            # finished, and the vision path does not need one.
            if not self.unit and not (self._is_a_count() or self._from_a_table()):
                out.append("no unit")
        if self.value is not None and self.value != self.value:  # NaN
            out.append("value is NaN")
        if not 0.0 <= self.confidence <= 1.0:
            out.append(f"confidence out of range: {self.confidence}")
        if self.provenance is None:
            out.append("no provenance")
        elif not self.provenance.source_text.strip():
            out.append("no source text -- claim is not checkable")
        return out

    def _from_a_table(self) -> bool:
        """Read off a table image rather than out of a sentence."""
        return bool(self.provenance and self.provenance.path == "vision")

    def _is_a_count(self) -> bool:
        """Does this parameter name the thing it counts?

        Deliberately generous, because the cost of being wrong is asymmetric: a
        counted record wrongly let through is a record with an empty unit, which
        every chart already handles, while one wrongly rejected is data lost with
        no trace.
        """
        name = self.parameter.lower()
        return bool(_COUNTED_PARAMETER.search(name))

    @property
    def is_usable(self) -> bool:
        return not self.problems()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["key"] = self.key
        if self.provenance:
            d["provenance"] = self.provenance.to_dict()
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


@dataclass
class Word:
    """One OCR'd word and where it sits on the scan.

    Carried so a claim can be highlighted *on the page image* rather than merely
    linked to it. Coordinates are in the scan's own pixel space.
    """

    text: str
    x0: int
    y0: int
    x1: int
    y1: int


@dataclass
class PageText:
    """One page of OCR, carrying its position so provenance survives.

    Page boundaries come from the item's `_djvu.xml`, not from form feeds --
    the plain `_djvu.txt` export has no page markers at all (verified: zero form
    feeds across sampled items), so anything relying on them silently collapses a
    500-page report into one page and destroys provenance.
    """

    identifier: str
    page: int                          # 1-indexed
    text: str
    width: int | None = None           # scan pixel dimensions, for box overlays
    height: int | None = None
    words: list[Word] = field(default_factory=list)

    #: 0..1, derived from archive.org's per-word `x-confidence` penalties. This
    #: is how legible the *scan* was, independent of how confident the model is
    #: about what the sentence meant -- the two multiply into the reading
    #: uncertainty that has to reach every trend line.
    ocr_confidence: float | None = None

    @property
    def char_count(self) -> int:
        return len(self.text)

    def find_boxes(self, phrase: str) -> list[Word]:
        """Words comprising `phrase`, so the source sentence can be drawn on the scan.

        Matching is loose on purpose: OCR mangles spacing and punctuation, and a
        highlight that is slightly off is far more useful than no highlight.

        The phrase is split on whitespace and each token then stripped of
        punctuation, rather than split on punctuation directly. Splitting on
        `\\W+` turned "Commission's" into two targets where the page holds one
        word, so the run stopped dead at the apostrophe and fell back to the few
        words before it. Any quote containing an apostrophe -- which is a great
        many of them -- cropped to its opening fragment.
        """
        if not self.words or not phrase.strip():
            return []
        target = [t for t in (re.sub(r"\W+", "", w.lower()) for w in phrase.split()) if t]
        if not target:
            return []
        norm = [re.sub(r"\W+", "", w.text.lower()) for w in self.words]
        n = len(target)
        for i in range(len(norm) - n + 1):
            if norm[i:i + n] == target:
                return self.words[i:i + n]
        # Fall back to the longest run that matches the opening of the phrase.
        for length in range(min(n, len(norm)), 2, -1):
            head = target[:length]
            for i in range(len(norm) - length + 1):
                if norm[i:i + length] == head:
                    return self.words[i:i + length]
        return []
