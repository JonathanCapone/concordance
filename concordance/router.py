"""The page router.

Measured across a 219-item random sample of the whole collection:

    mixed      55.3%   narrative and tables in the same document
    narrative  35.2%   prose extraction works
    tabular     9.6%   needs vision extraction off the page image

Because most documents are mixed, routing has to happen per *page*. A
document-level classifier would send a 1969 annual report down one path and
discard whichever half didn't match.

Routing is deliberately cheap and local -- no model call. It runs over the whole
OCR corpus to decide which pages are worth spending a model on, so it must be
fast and it must fail toward inclusion: a page wrongly sent to a model costs
fractions of a cent, a page wrongly skipped is data lost silently.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from enum import Enum

from .models import PageText


class Path(str, Enum):
    """Where a page gets sent. A page may match several."""

    PROSE = "prose"          # A -- sentences carrying measurements
    TABLE = "table"          # B -- vision extraction off the scan
    STANDARD = "standard"    # C -- regulatory limits of the era
    FIGURE = "figure"        # D -- read a plotted line back into numbers
    MAP = "map"              # E -- georeference as an overlay
    SKIP = "skip"            # nothing worth spending a model on


WORD_RE = re.compile(r"[A-Za-z]{3,}")
NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")

#: Units seen in the corpus. Presence of a unit next to a number is the single
#: strongest signal that a page carries measurements rather than prose about them.
UNIT_RE = re.compile(
    r"\b(mg/[lL1]|ug/m3?|µg/m3?|ppm|ppb|mgd|m3/d|cfs|cu\.?\s?ft|gal(?:lons)?|"
    r"mg/kg|kg/ha|tonnes?|hectares?|acres?|°[CF]|per ?cent|%)\b",
    re.I,
)

#: A number and the thing it counts. In most of this archive the unit IS the
#: noun -- "75 elementary schools", "1,243 dwellings", "42 teachers" -- and
#: requiring an explicit unit like mg/L is why a pipeline built on water reports
#: was blind to education, housing, agriculture, health and justice records.
#:
#: This is a routing heuristic, not a vocabulary. Being wrong here costs a page
#: of model time; being wrong in `parameters.py` corrupts a measurement. The two
#: deserve different standards of evidence, so this list is deliberately broad
#: and covers the veins the corpus actually holds rather than the ones the first
#: extraction happened to start with.
COUNTED_RE = re.compile(
    r"\b\d[\d,]*\s+(?:\w+\s+){0,3}?("
    r"schools?|pupils?|students?|teachers?|classrooms?|graduates?|candidates?|"
    r"dwellings?|households?|families|persons?|people|residents?|inhabitants?|"
    r"beds?|patients?|physicians?|nurses?|hospitals?|"
    r"farms?|cattle|swine|poultry|livestock|head|bushels?|"
    r"employees?|workers?|members?|officers?|staff|"
    r"births?|deaths?|cases?|complaints?|applications?|appeals?|convictions?|"
    r"vehicles?|accidents?|licen[cs]es?|permits?|claims?|"
    r"lots?|units?|rooms?|buildings?|plants?|wells?|mines?|"
    r"municipalities|townships?|counties|libraries|volumes?"
    r")\b",
    re.I,
)

#: A regulatory limit rather than an observation. Keeping these apart matters:
#: you cannot say whether 104 mg/L was bad without the standard *of that year*.
STANDARD_RE = re.compile(
    r"\b(maximum acceptable concentration|objective|criteri(?:on|a)|guideline|"
    r"standard|limit|shall not exceed|must not exceed|permissible|"
    r"recommended (?:level|concentration)|MAC\b|ODWO)\b",
    re.I,
)

FIGURE_RE = re.compile(
    r"\b(figure|fig\.|graph|plotted|plot of|curve|histogram|chart)\s*\.?\s*\d*",
    re.I,
)

MAP_RE = re.compile(
    r"\b(map|scale 1[:\s]|1:\d{3,}|legend|contour|latitude|longitude|"
    r"UTM|township|concession|quadrangle|sheet \d)\b",
    re.I,
)

#: Front matter, scanning artefacts and library boilerplate. Cheap to drop and
#: it is a meaningful share of every scanned item.
BOILERPLATE_RE = re.compile(
    r"(digitized by the internet archive|copyright provisions|table of contents|"
    r"this page intentionally|library and archives|call number|"
    r"^\s*contents\s*$)",
    re.I | re.M,
)


@dataclass
class PageSignals:
    """The measured features behind a routing decision.

    Kept on the result so a surprising route can be explained rather than
    guessed at -- the router runs over millions of pages and will be wrong
    sometimes, and wrong-and-inspectable beats wrong-and-opaque.
    """

    chars: int
    words: int
    numbers: int
    digit_ratio: float
    prose_ratio: float
    table_ratio: float
    has_units: bool
    unit_hits: int
    counted_hits: int
    standard_hits: int
    figure_hits: int
    map_hits: int
    boilerplate: bool


#: Narrowest line width that can still count as prose, and the widest we will
#: ever demand. The lower bound keeps a two-word index entry from reading as a
#: paragraph; the upper bound is the old fixed threshold, so full-width report
#: pages route exactly as they did before.
MIN_PROSE_WORDS = 4
MAX_PROSE_WORDS = 8


def prose_line_width(lines: list[str]) -> int:
    """How many words make a line prose *on this page*.

    A fixed threshold is a statement about typography, not about content, and
    this one was quietly throwing away a quarter of the archive. "Hamilton: An
    Adventure in Good Living" (1983) is a city magazine set in narrow columns:
    149 lines of unbroken prose on one page, median 4 words to the line, not one
    of them reaching 8. It scored prose_ratio 0.000 and every page of it was
    skipped -- including one carrying "75 elementary schools under the aegis of
    the Hamilton Board of Education, and 42 operated by the Hamilton-Wentworth
    Roman Catholic Separate School Board", which is exactly the kind of number
    nobody has in a database.

    Measured over 5,388 pages from 30 random items: 28.5% of ALL pages were
    running text discarded on line width alone. Extrapolated over the corpus,
    roughly 6.3 million pages. The categories worst hit are the deliberative
    ones -- committee agendas, royal commission hearings, sessional papers,
    legislative journals -- because that is how minutes have always been set.

    So the threshold now comes from the page's own median line, clamped. Wide
    pages behave exactly as before; narrow ones stop being invisible.
    """
    counts = [len(WORD_RE.findall(ln)) for ln in lines]
    if not counts:
        return MAX_PROSE_WORDS
    median = statistics.median(counts)
    return int(max(MIN_PROSE_WORDS, min(MAX_PROSE_WORDS, median)))


def signals(page: PageText) -> PageSignals:
    text = page.text
    lines = [ln for ln in text.split("\n") if ln.strip()] or [text]

    words = len(WORD_RE.findall(text))
    numbers = len(NUM_RE.findall(text))
    digits = sum(c.isdigit() for c in text)
    letters = sum(c.isalpha() for c in text)

    min_words = prose_line_width(lines)
    prose_lines = sum(
        1 for ln in lines
        if len(WORD_RE.findall(ln)) >= min_words and len(NUM_RE.findall(ln)) <= 3
    )
    table_lines = sum(
        1 for ln in lines if len(NUM_RE.findall(ln)) >= 5 and len(WORD_RE.findall(ln)) <= 4
    )

    unit_hits = len(UNIT_RE.findall(text))
    counted_hits = len(COUNTED_RE.findall(text))
    return PageSignals(
        chars=len(text),
        words=words,
        numbers=numbers,
        digit_ratio=digits / max(1, digits + letters),
        prose_ratio=prose_lines / len(lines),
        table_ratio=table_lines / len(lines),
        # A counted noun is a unit. Keeping them in one flag means every gate
        # that asks "does this page state a quantity" gets the same answer.
        has_units=(unit_hits + counted_hits) > 0,
        unit_hits=unit_hits,
        counted_hits=counted_hits,
        standard_hits=len(STANDARD_RE.findall(text)),
        figure_hits=len(FIGURE_RE.findall(text)),
        map_hits=len(MAP_RE.findall(text)),
        boilerplate=bool(BOILERPLATE_RE.search(text)),
    )


@dataclass
class Route:
    page: PageText
    paths: list[Path]
    signals: PageSignals

    @property
    def worth_reading(self) -> bool:
        return bool(self.paths) and self.paths != [Path.SKIP]


def route(page: PageText) -> Route:
    """Decide which extraction paths a page deserves.

    Biased toward inclusion. A page sent to a model needlessly costs a fraction
    of a cent; a page skipped wrongly is data lost with no trace, which is the
    failure mode this whole project exists to reverse.
    """
    s = signals(page)
    paths: list[Path] = []

    # Too little text to be anything. Note this does NOT mean "no content" --
    # a full-page map or photograph lands here with almost no OCR, which is
    # exactly why the map check runs before the length gate.
    if s.map_hits >= 2 and s.chars < 1200:
        return Route(page, [Path.MAP], s)

    if s.chars < 120:
        return Route(page, [Path.SKIP], s)

    if s.boilerplate and s.numbers < 5:
        return Route(page, [Path.SKIP], s)

    # A -- prose carrying measurements. Units are the discriminator: prose
    # *about* pollution is common, prose *reporting* a value is what we want.
    if s.prose_ratio >= 0.15 and s.has_units:
        paths.append(Path.PROSE)

    # C -- regulatory limits. Frequently sit in the same paragraph as
    # observations, so this is additive rather than exclusive.
    if s.standard_hits >= 1 and s.has_units:
        paths.append(Path.STANDARD)

    # B -- dense numeric pages. These are where 2013-era OCR failed hardest and
    # where a modern vision model earns its cost.
    if s.table_ratio >= 0.08 or (s.digit_ratio >= 0.30 and s.numbers >= 20):
        paths.append(Path.TABLE)

    # D -- figures. The numbers behind a plotted line were often never tabulated
    # anywhere, so the picture is the only surviving copy of the data.
    if s.figure_hits >= 1 and s.digit_ratio < 0.30:
        paths.append(Path.FIGURE)

    # E -- cartographic pages.
    if s.map_hits >= 3:
        paths.append(Path.MAP)

    # Prose with no units still gets read if it is substantial: 1960s reports
    # often state a value in words ("just over three million gallons").
    if not paths and s.prose_ratio >= 0.30 and s.numbers >= 3:
        paths.append(Path.PROSE)

    return Route(page, paths or [Path.SKIP], s)


def route_item(pages: list[PageText]) -> list[Route]:
    return [route(p) for p in pages]


def summarize(routes: list[Route]) -> dict[str, int]:
    """Counts per path, for reporting what a pass actually decided."""
    out: dict[str, int] = {p.value: 0 for p in Path}
    for r in routes:
        for p in r.paths:
            out[p.value] += 1
    return out
