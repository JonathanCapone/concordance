"""Conservative publication-year inference from scanned OCR text.

The archive catalogue is missing a year for roughly a third of this corpus.
Dates are common in the OCR, but most of them are *not* publication dates: a
report can discuss older measurements, cite newer forecasts, carry a library
stamp, or contain a four-digit station number.  This module therefore extracts
only structurally supported candidates, ranks them by meaning rather than by
numeric value, and abstains when equally strong evidence disagrees.

The returned evidence is always one contiguous, verbatim slice of the supplied
OCR.  Results are proposals; this module neither mutates catalogue records nor
writes metadata back to the Internet Archive.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .models import PageText


_YEAR_TEXT = r"(?:1[7-9]\d{2}|20(?:0\d|1\d|2\d))"
_YEAR = re.compile(rf"(?<![A-Za-z0-9.])(?P<year>{_YEAR_TEXT})(?![A-Za-z0-9])")
_RANGE = re.compile(
    rf"(?<![A-Za-z0-9.])(?P<first>{_YEAR_TEXT})\s*[-/–—]\s*"
    rf"(?P<last>{_YEAR_TEXT})(?![A-Za-z0-9])"
)

_MONTH = (
    r"jan(?:uary|vier)?|feb(?:ruary|ruary)?|mar(?:ch|s)?|apr(?:il)?|may|"
    r"jun(?:e|in)?|jul(?:y|let)?|aug(?:ust)?|sep(?:t(?:ember|embre)?)?|"
    r"oct(?:ober|obre)?|nov(?:ember|embre)?|dec(?:ember|embre)?|"
    r"f[ée]vrier|fÃ©vrier|avril|mai|juin|juillet|ao[ûu]t|aoÃ»t|"
    r"d[ée]cembre|dÃ©cembre"
)
_MONTH_YEAR = re.compile(
    rf"(?i)(?<![A-Za-z])(?:{_MONTH})\.?\s*,?\s*(?P<year>{_YEAR_TEXT})(?![A-Za-z0-9])"
)
_FULL_DATE = re.compile(
    rf"(?ix)(?:"
    rf"(?:{_MONTH})\.?\s+\d{{1,2}}(?:st|nd|rd|th|er)?\s*,?\s*"
    rf"(?P<month_first>{_YEAR_TEXT})(?![A-Za-z0-9])"
    rf"|(?:le\s+)?\d{{1,2}}(?:st|nd|rd|th|er)?\s+(?:{_MONTH})\.?\s*,?\s*"
    rf"(?P<day_first>{_YEAR_TEXT})(?![A-Za-z0-9])"
    rf")"
)
_STANDALONE_YEAR = re.compile(rf"^\s*(?P<year>{_YEAR_TEXT})\s*[.,;:]?\s*$")

_COPYRIGHT = re.compile(
    r"(?i)(?:\bcopyright\b|\bcopr\.?\b|\N{COPYRIGHT SIGN}|droits?\s+d[\N{APOSTROPHE}\N{RIGHT SINGLE QUOTATION MARK}]auteur)"
)
_PUBLICATION = re.compile(
    r"(?ix)(?:"
    r"^\s*[^A-Za-z0-9]{0,5}(?:"
    r"published\b|printed\b|publication\s+date\b|date\s+de\s+publication\b|"
    r"publi(?:e|[ée]|Ã©)e?\b|imprim(?:e|[ée]|Ã©)e?\b|"
    r"d(?:e|[ée]|Ã©)p[oô]t\s+l(?:e|[ée]|Ã©)gal\b|"
    r"(?:queen|king)[\N{APOSTROPHE}\N{RIGHT SINGLE QUOTATION MARK}]s\s+printer\b|"
    r"imprimeur\s+(?:de\s+la\s+reine|du\s+roi)\b|"
    r"minister\s+of\s+supply\s+and\s+services\s+canada\b"
    r")"
    r")"
)
_REVISION = re.compile(
    r"(?i)^\s*(?:revised|revision|reprinted|(?:first|second|third|fourth|fifth|"
    r"sixth|seventh|eighth|ninth|tenth|\d+(?:st|nd|rd|th))\s+printing|"
    r"printing\s*(?:date)?|edition)\b"
)
_ANNUAL = re.compile(
    r"(?ix)(?:"
    r"\bannual\s+report\b|\brapport\s+annuel\b|\breporting\s+(?:year|period)\b|"
    r"\bfiscal\s+year\b|\bfor\s+the\s+year\s+ended\b|"
    r"\bfinancial\s+statements?\s+for\s+the\s+year\s+ended\b|"
    r"\b(?:year|exercice)\s+(?:ended|ending|termin[ée])\b"
    r")"
)
_LETTER_ADDRESSEE = re.compile(
    r"(?ix)(?:"
    r"\bdear\b|\bdear\s+(?:sir|madam)\b|\bmonsieur\b|\bmadame\b|"
    r"\bthe\s+honou?rable\b|\bto\s*:\s*(?:the\s+)?(?:chair|minister|commissioner)|"
    r"\bmonsieur\s+le\s+ministre\b"
    r")"
)
_LETTER_TRANSMITTAL = re.compile(
    r"(?ix)(?:"
    r"\bi\s+have\s+the\s+honou?r\b|\bj[\N{APOSTROPHE}\N{RIGHT SINGLE QUOTATION MARK}]ai\s+l[\N{APOSTROPHE}\N{RIGHT SINGLE QUOTATION MARK}]honneur\b|"
    r"\benclosed\b|\bi\s+(?:enclose|submit|transmit)\b|\bsoumettre\b|"
    r"\byours\s+(?:truly|sincerely|faithfully)\b|\brespectfully\b|"
    r"\bsalutations\s+distingu[ée]es\b"
    r")"
)
_NOT_A_LETTER = re.compile(
    r"(?i)(?:\bbalance\b|\byear\s+ended\b|\bfiscal\s+year\b|"
    r"\bfinancial\s+statements?\b|\bas\s+at\b|\btable(?:au)?\b)"
)
_DIGITIZATION = re.compile(
    r"(?i)(?:digitiz|digitis|scann(?:ed|ing)|upload(?:ed|ing)?|internet\s+archive|"
    r"archive\.org|electronic\s+edition|funding\s+from)"
)
_FUTURE_TABLE = re.compile(
    r"(?i)(?:project(?:ed|ion)|forecast|planned|proposed|scenario|target|"
    r"anticipated|future|pro\s+forma|estimate\s+for)"
)
_TABLE_HEADING = re.compile(r"(?i)\b(?:table|tableau)\s+[A-Z0-9IVX.-]+")
_TABLE_OF_CONTENTS = re.compile(r"(?i)\btable\s+of\s+contents\b|table\s+des\s+mati")
_NUMBER = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)?(?![A-Za-z])")
_LIBRARY_STAMP_DATE = re.compile(
    rf"(?i)^\s*(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)\.?”
    rf"\s+\d{{1,2}}\s+{_YEAR_TEXT}\s*(?:\.\.\.)?[-.]*\s*$"
)


@dataclass
class DateGuess:
    """One reviewable publication-year proposal.

    ``evidence`` must be copied literally from the supplied OCR whenever a year
    is proposed.  ``alternatives`` contains only other defensible date
    candidates, not every four-digit token in the document.
    """

    year: int | None
    confidence: float
    basis: str
    evidence: str
    alternatives: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be finite and between 0 and 1")
        if self.year is not None:
            if not 1700 <= self.year <= 2029:
                raise ValueError("year must be between 1700 and 2029")
            if not self.evidence:
                raise ValueError("a proposed year requires verbatim evidence")
        if self.year in self.alternatives:
            raise ValueError("the proposed year cannot also be an alternative")
        if len(self.alternatives) != len(set(self.alternatives)):
            raise ValueError("alternatives must be unique")

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON-ready public representation."""
        return {
            "year": self.year,
            "confidence": self.confidence,
            "basis": self.basis,
            "evidence": self.evidence,
            "alternatives": list(self.alternatives),
        }


@dataclass(frozen=True)
class _Source:
    text: str
    page: int | None
    base: int
    physical_pages: bool
    ocr_confidence: float | None


@dataclass(frozen=True)
class _Line:
    source: _Source
    index: int
    raw: str
    start: int
    end: int

    @property
    def evidence(self) -> str:
        return self.raw.strip()

    @property
    def position(self) -> int:
        return self.source.base + self.start


@dataclass(frozen=True)
class _Candidate:
    year: int
    confidence: float
    tier: int
    basis: str
    evidence: str
    offset: int
    alternatives: tuple[int, ...] = ()
    lower_bound: bool = False
    revision: bool = False
    ocr_confidence: float | None = None


def _sources(value: str | Sequence[PageText] | None) -> list[_Source]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_Source(value, None, 0, False, None)] if value else []

    supplied = list(value)
    # One PageText can be Archive.pages()' synthetic whole-document fallback.
    # Requiring multiple pages prevents that fallback from being labelled a
    # proven title page merely because its synthetic page number is one.
    physical = len(supplied) > 1
    out: list[_Source] = []
    base = 0
    for position, page in enumerate(supplied, 1):
        text = getattr(page, "text", "")
        if not isinstance(text, str) or not text:
            continue
        number = getattr(page, "page", position)
        number = number if isinstance(number, int) else position
        confidence = getattr(page, "ocr_confidence", None)
        confidence = confidence if isinstance(confidence, (int, float)) else None
        out.append(_Source(text, number, base, physical, confidence))
        base += len(text) + 1
    return out


def _lines(source: _Source) -> list[_Line]:
    out: list[_Line] = []
    cursor = 0
    for index, chunk in enumerate(source.text.splitlines(keepends=True)):
        raw = chunk.rstrip("\r\n")
        out.append(_Line(source, index, raw, cursor, cursor + len(raw)))
        cursor += len(chunk)
    if not out and source.text:
        out.append(_Line(source, 0, source.text, 0, len(source.text)))
    return out


def _front(line: _Line, kind: str) -> bool:
    source = line.source
    if source.physical_pages:
        page = source.page or 10_000
        if kind == "publication":
            return page <= 4
        if kind == "copyright":
            return page <= 12
        if kind in {"letter", "title"}:
            return page <= 12
        return page <= 20

    limit = {
        "publication": 4_000,
        "copyright": 12_000,
        "letter": 12_000,
        "title": 12_000,
        "annual": 30_000,
    }[kind]
    return line.position <= limit


def _year_matches(text: str) -> list[re.Match[str]]:
    return list(_YEAR.finditer(text))


def _reject_year_context(text: str, match: re.Match[str]) -> bool:
    """Reject common four-digit identifiers, stamps, laws, and measurements."""
    lower = text.lower()
    year = re.escape(match.group("year"))
    start, end = match.span("year")
    before = lower[max(0, start - 80) : start]
    after = lower[end : min(len(lower), end + 45)]

    if _DIGITIZATION.search(text):
        return True
    if re.search(r"\bcopyright\s+act\b", lower):
        return True
    if re.search(r"\b(?:received|accessioned|acquired)\b", lower):
        return True
    if re.search(rf"\b(?:act|regulation|statute)\s*,?\s*{year}\b", lower):
        return True
    if re.search(rf"\br\.?s\.?o\.?\s*{year}\b", lower):
        return True
    if re.search(rf"\([^)]{{0,60}},\s*{year}\s*\)", lower):
        return True

    identifier = re.search(
        r"(?:project|contract|station|site|sample|file|drawing|job|account|"
        r"specification|catalogue|catalog|cat\.?|inventory|isbn|issn|accession)"
        r"\s*(?:no\.?|number|#)?\s*[A-Za-z0-9./:-]*$",
        before,
    )
    report_number = re.search(r"report\s*(?:no\.?|number|#)\s*[A-Za-z0-9./:-]*$", before)
    if identifier or report_number:
        return True

    if re.match(
        r"\s*(?:gal|gallons?|mg|kg|lb|lbs|m3|m\N{SUPERSCRIPT THREE}|ft|feet|"
        r"litres?|liters?|l/day|mg/l|ppm|ppb|cfs|kw|volts?)\b",
        after,
    ):
        return True
    if re.match(
        r"\s+(?:street|st\.?|road|rd\.?|avenue|ave\.?|boulevard|blvd\.?|"
        r"drive|dr\.?|highway|hwy\.?|route)\b",
        after,
    ):
        return True
    return False


def _candidate(
    *,
    match: re.Match[str],
    line: _Line,
    confidence: float,
    tier: int,
    basis: str,
    evidence: str | None = None,
    alternatives: tuple[int, ...] = (),
    lower_bound: bool = False,
    revision: bool = False,
) -> _Candidate | None:
    if _reject_year_context(line.raw, match):
        return None
    year = int(match.group("year"))
    return _Candidate(
        year=year,
        confidence=confidence,
        tier=tier,
        basis=basis,
        evidence=evidence if evidence is not None else line.evidence,
        offset=line.position + match.start("year"),
        alternatives=alternatives,
        lower_bound=lower_bound,
        revision=revision,
        ocr_confidence=line.source.ocr_confidence,
    )


def _exact_slice(lines: list[_Line], first: int, last: int) -> str:
    """One contiguous source slice, including its original newline spelling."""
    source = lines[first].source
    return source.text[lines[first].start : lines[last].end].strip()


def _extract_explicit(lines: list[_Line]) -> list[_Candidate]:
    out: list[_Candidate] = []
    for line in lines:
        evidence = line.evidence
        if not evidence or len(evidence) > 280 or not _year_matches(line.raw):
            continue
        if _DIGITIZATION.search(line.raw) or re.search(r"(?i)\bcopyright\s+act\b", line.raw):
            continue

        copyright_line = bool(_COPYRIGHT.search(line.raw)) and _front(line, "copyright")
        revision_line = bool(_REVISION.search(line.raw)) and (
            line.position <= 25_000
            or line.position >= max(0, line.source.base + len(line.source.text) - 12_000)
        )
        publication_match = _PUBLICATION.search(line.raw)
        # In body prose, "reports were published for 1986" describes another
        # publication.  An original imprint is normally a short label at the
        # start of its line; requiring a local anchor also blocks that common
        # false positive near the end of nominal front matter.
        publication_line = bool(
            publication_match
            and publication_match.start() <= 40
            and _front(line, "publication")
        )
        if not (copyright_line or revision_line or publication_line):
            continue

        if copyright_line:
            basis, confidence, revision = "copyright line", 0.96, False
        else:
            basis, confidence, revision = "publication line", 0.94, revision_line
        for match in _year_matches(line.raw):
            found = _candidate(
                match=match,
                line=line,
                confidence=confidence,
                tier=1,
                basis=basis,
                revision=revision,
            )
            if found:
                out.append(found)
    return out


def _extract_letters(lines: list[_Line]) -> list[_Candidate]:
    out: list[_Candidate] = []
    for index, line in enumerate(lines):
        if not _front(line, "letter"):
            continue
        date_matches = list(_FULL_DATE.finditer(line.raw))
        if not date_matches:
            continue
        first = max(0, index - 2)
        last = min(len(lines) - 1, index + 4)
        context = _exact_slice(lines, first, last)
        if not _LETTER_CUE.search(context) or _NOT_A_LETTER.search(context):
            continue
        for date_match in date_matches:
            year_match = next(
                (m for m in _year_matches(line.raw) if m.start() >= date_match.start()),
                None,
            )
            if year_match is None:
                continue
            found = _candidate(
                match=year_match,
                line=line,
                confidence=0.88,
                tier=2,
                basis="covering letter",
                evidence=context,
            )
            if found:
                out.append(found)
    return out


def _looks_like_front_date(line: str, date_match: re.Match[str]) -> bool:
    """Distinguish a dateline/title date from a date embedded in prose."""
    before = line[: date_match.start()].strip()
    after = line[date_match.end() :].strip()
    if after and not re.fullmatch(r"[.,;:()\[\]-]+", after):
        return False
    if not before:
        return True
    if len(before) <= 24 and not re.search(r"(?i)\b(?:in|during|since|from)\s*$", before):
        return True
    if re.match(
        r"(?i)^\s*(?:no\.?|number|issue|bulletin|ottawa|toronto|montreal|"
        r"quebec|ontario|canada)\b",
        before,
    ):
        return True
    letters = [character for character in before if character.isalpha()]
    return bool(letters) and sum(character.isupper() for character in letters) / len(letters) >= 0.8


def _extract_front_dates(lines: list[_Line]) -> list[_Candidate]:
    out: list[_Candidate] = []
    for line in lines:
        if not _front(line, "title"):
            continue
        evidence = line.evidence
        if not evidence or len(evidence) > 180:
            continue
        if _COPYRIGHT.search(line.raw) or _PUBLICATION.search(line.raw) or _REVISION.search(line.raw):
            continue
        if _ANNUAL.search(line.raw) or _NOT_A_LETTER.search(line.raw):
            continue
        if _DIGITIZATION.search(line.raw) or re.search(
            r"(?i)\b(?:received|accessioned|library\s+stamp)\b", line.raw
        ):
            continue

        date_matches = list(_FULL_DATE.finditer(line.raw)) or list(
            _MONTH_YEAR.finditer(line.raw)
        )
        if not date_matches:
            standalone = _STANDALONE_YEAR.match(line.raw)
            date_matches = [standalone] if standalone else []
        if not date_matches:
            continue

        date_matches = [
            match for match in date_matches if match and _looks_like_front_date(line.raw, match)
        ]
        if not date_matches:
            continue

        basis = "title page" if line.source.physical_pages else "front matter date"
        if line.source.physical_pages:
            confidence = 0.84
        elif any(_FULL_DATE.fullmatch(m.group(0)) for m in date_matches):
            confidence = 0.80
        else:
            confidence = 0.77
        for date_match in date_matches:
            year_match = next(
                (
                    m
                    for m in _year_matches(line.raw)
                    if date_match.start() <= m.start() < date_match.end()
                ),
                None,
            )
            if year_match is None:
                continue
            found = _candidate(
                match=year_match,
                line=line,
                confidence=confidence,
                tier=3,
                basis=basis,
            )
            if found:
                out.append(found)
    return out


def _extract_annual(lines: list[_Line]) -> list[_Candidate]:
    out: list[_Candidate] = []
    for line in lines:
        if not _front(line, "annual") or not _ANNUAL.search(line.raw):
            continue
        evidence = line.evidence
        if not evidence or len(evidence) > 320:
            continue
        ranges = list(_RANGE.finditer(line.raw))
        if ranges:
            for period in ranges:
                first, last = int(period.group("first")), int(period.group("last"))
                chosen = max(first, last)
                year_match = next(
                    m for m in _year_matches(line.raw) if int(m.group("year")) == chosen
                )
                found = _candidate(
                    match=year_match,
                    line=line,
                    confidence=0.72,
                    tier=4,
                    basis="annual report period",
                    alternatives=(min(first, last),),
                )
                if found:
                    out.append(found)
            continue

        for match in _year_matches(line.raw):
            found = _candidate(
                match=match,
                line=line,
                confidence=0.76,
                tier=4,
                basis="annual report period",
            )
            if found:
                out.append(found)
    return out


def _extract_tables(lines: list[_Line]) -> list[_Candidate]:
    out: list[_Candidate] = []
    for index, heading in enumerate(lines):
        if not _TABLE_HEADING.search(heading.raw) or _TABLE_OF_CONTENTS.search(heading.raw):
            continue
        window = lines[index : min(len(lines), index + 18)]
        block = _exact_slice(lines, index, index + len(window) - 1)
        if _FUTURE_TABLE.search(block) or re.search(
            r"(?i)\b(?:bibliography|references|literature\s+cited)\b", block
        ):
            continue

        matches: list[tuple[_Line, re.Match[str]]] = []
        numeric_rows = 0
        horizontal_years = False
        for line in window:
            line_years = [
                match
                for match in _year_matches(line.raw)
                if not _reject_year_context(line.raw, match)
            ]
            matches.extend((line, match) for match in line_years)
            if line_years and len(_NUMBER.findall(line.raw)) >= 2:
                numeric_rows += 1
            if len({int(m.group("year")) for m in line_years}) >= 3:
                horizontal_years = True

        years = {int(match.group("year")) for _, match in matches}
        if len(years) < 3 or (numeric_rows < 3 and not horizontal_years):
            continue
        latest = max(years)
        line, match = next(
            (pair for pair in reversed(matches) if int(pair[1].group("year")) == latest)
        )
        found = _candidate(
            match=match,
            line=line,
            confidence=0.30,
            tier=5,
            basis="latest data year (lower bound)",
            lower_bound=True,
        )
        if found:
            out.append(found)
    return out


def _deduplicate(candidates: list[_Candidate]) -> list[_Candidate]:
    seen: set[tuple[int, int, str, str, int]] = set()
    out: list[_Candidate] = []
    for candidate in candidates:
        key = (
            candidate.year,
            candidate.tier,
            candidate.basis,
            candidate.evidence,
            candidate.offset,
        )
        if key not in seen:
            seen.add(key)
            out.append(candidate)
    return out


def _alternative_years(
    candidates: list[_Candidate], chosen: _Candidate | None = None
) -> list[int]:
    years: list[int] = []
    if chosen:
        years.extend(chosen.alternatives)
    for candidate in sorted(candidates, key=lambda c: (c.tier, c.offset, c.year)):
        years.extend(candidate.alternatives)
        years.append(candidate.year)
    excluded = chosen.year if chosen else None
    return list(dict.fromkeys(year for year in years if year != excluded))


def _resolve(candidates: list[_Candidate]) -> DateGuess:
    if not candidates:
        return DateGuess(None, 0.0, "no defensible date", "")

    candidates = _deduplicate(candidates)
    top_tier = min(candidate.tier for candidate in candidates)
    top = [candidate for candidate in candidates if candidate.tier == top_tier]
    top_years = {candidate.year for candidate in top}

    if len(top_years) > 1 and top_tier == 1:
        # A clearly labelled revision or later printing supersedes an original
        # copyright year.  Without that explicit relationship, two publication
        # events may be a bound volume and are not safe to collapse.
        revisions = [candidate for candidate in top if candidate.revision]
        if len(revisions) == 1 and revisions[0].year == max(top_years):
            chosen = revisions[0]
        else:
            return DateGuess(
                None,
                0.0,
                "conflicting evidence",
                "",
                _alternative_years(candidates),
            )
    elif len(top_years) > 1 and top_tier == 5:
        # Several observed tables collectively establish the latest lower bound.
        chosen = max(top, key=lambda candidate: (candidate.year, -candidate.offset))
    elif len(top_years) > 1:
        return DateGuess(
            None,
            0.0,
            "conflicting evidence",
            "",
            _alternative_years(candidates),
        )
    else:
        chosen = max(top, key=lambda candidate: (candidate.confidence, -candidate.offset))

    lower_bounds = [candidate for candidate in candidates if candidate.lower_bound]
    if chosen.tier < 5 and lower_bounds:
        latest_bound = max(candidate.year for candidate in lower_bounds)
        if latest_bound > chosen.year:
            return DateGuess(
                None,
                0.0,
                "conflicting evidence",
                "",
                _alternative_years(candidates),
            )

    confidence = chosen.confidence
    corroborating = {
        candidate.basis
        for candidate in candidates
        if candidate.year == chosen.year and candidate.basis != chosen.basis
    }
    confidence = min(0.99, confidence + 0.01 * len(corroborating))
    # Page OCR confidence is a coarse readability measure, not a calibrated
    # probability.  Only extremely poor pages cap our semantic confidence;
    # unknown or ordinary OCR quality is left alone.
    if chosen.ocr_confidence is not None and chosen.ocr_confidence < 0.5:
        confidence = min(confidence, 0.60)
    return DateGuess(
        chosen.year,
        round(confidence, 4),
        chosen.basis,
        chosen.evidence,
        _alternative_years(candidates, chosen),
    )


def infer_year_from_text(
    item: Mapping[str, Any],
    pages_or_text: str | Sequence[PageText] | None,
) -> DateGuess:
    """Infer an original publication year from OCR, or explicitly abstain.

    The item's title, date, identifier, and other metadata are deliberately not
    used as evidence.  A truthy existing ``year`` is only an overwrite guard;
    held-out validation removes that field before calling this function.
    """
    if item.get("year"):
        return DateGuess(None, 0.0, "already has a year", "")

    sources = _sources(pages_or_text)
    if not sources:
        return DateGuess(None, 0.0, "no defensible date", "")

    candidates: list[_Candidate] = []
    for source in sources:
        lines = _lines(source)
        candidates.extend(_extract_explicit(lines))
        candidates.extend(_extract_letters(lines))
        candidates.extend(_extract_front_dates(lines))
        candidates.extend(_extract_annual(lines))
        candidates.extend(_extract_tables(lines))
    return _resolve(candidates)
