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


# These bounds are part of this corpus contract, not a claim that government
# publishing began in 1841.  Numbers outside the archive's documented
# 1841--2013 span are more likely historical references or OCR damage than a
# missing catalogue year.
MIN_PUBLICATION_YEAR = 1841
MAX_PUBLICATION_YEAR = 2013
_YEAR_TEXT = r"(?:184[1-9]|18[5-9]\d|19\d{2}|200\d|201[0-3])"
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
    r"\bannual\s+report\b|\brapport\s+annuel\b|"
    r"^\s*reporting\s+(?:year|period)\s*[:.-]|"
    r"^\s*(?:report\s+)?for\s+the\s+year\s+ended\b|"
    r"^\s*fiscal\s+year\s+(?:ended|ending)\b|"
    r"\bfinancial\s+statements?\s+for\s+the\s+year\s+ended\b|"
    r"^\s*this\s+report\s+(?:contains|presents?)\b[^\n]{0,100}\bfor\b"
    r")"
)
_REPORTING_TITLE = re.compile(
    rf"(?ix)(?:"
    rf"^\s*{_YEAR_TEXT}\s+(?:[A-Z&'’-]+\s+){{0,8}}REPORT\b|"
    rf"^\s*(?:REPORT|BULLETIN)\s+(?:FOR\s+)?{_YEAR_TEXT}\b"
    rf")"
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
    r"(?i)(?:\bbalance\b|\bas\s+at\b)"
)
_DIGITIZATION = re.compile(
    r"(?i)(?:digitiz|digitis|scann(?:ed|ing)|upload(?:ed|ing)?|internet\s+archive|"
    r"archive\.org|electronic\s+edition|funding\s+from)"
)
_FUTURE_TABLE = re.compile(
    r"(?i)(?:project(?:ed|ion)|forecast|planned|proposed|scenario|target|"
    r"anticipated|future|pro\s+forma|estimated|estimate\s+for)"
)
_TABLE_HEADING = re.compile(r"(?i)\b(?:table|tableau)\s+[A-Z0-9IVX.-]+")
_TABLE_OF_CONTENTS = re.compile(r"(?i)\btable\s+of\s+contents\b|table\s+des\s+mati")
_NUMBER = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)?(?![A-Za-z])")
_LIBRARY_STAMP_DATE = re.compile(
    rf"(?i)^\s*(?:\d{{1,4}}\s*[,;:-]?\s*)?"
    rf"(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)\.?"
    rf"\s+\d{{1,2}}\s+{_YEAR_TEXT}\s*(?:\.\.\.)?[-.]*\s*$"
)
_WEEKDAY_DATE = re.compile(
    r"(?i)^\s*(?:mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|"
    r"fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b"
)
_NON_PUBLICATION_DOCUMENT = re.compile(
    r"(?ix)(?:"
    r"\bagendas?\s*/?\s*minutes\b|\bcommittee\s+agendas?\b|"
    r"\b(?:meeting|minutes|agenda)\s+of\b|\b(?:meeting|committee)\s+agenda\b|"
    r"\b(?:inaugural|regular|special)\s+meeting\b|\bcouncil\s+met\b|"
    r"\bby[-\s]?law\s+(?:no\.?|number)\b|\bto\s+amend\s+.*by[-\s]?law\b"
    r")"
)
_NOT_FRONT_MATTER_CONTEXT = re.compile(
    r"(?ix)(?:"
    r"\blist\s+of\s+(?:tables|figures|appendices)\b|"
    r"\bsampling\s+(?:site|date)s?\b|\bmeeting\s+of\b|\bcouncil\s+met\b|"
    r"\bminutes\s+of\b|\bcommittee\s+meeting\b|\bresults?\s+of\s+voting\b|"
    r"\b(?:letter|correspondence)\s+(?:from|to)\b|"
    r"\b(?:public\s+)?hearing\b|\bagenda\b|\b(?:first|second|third|1st|2nd|3rd)\s+reading\b|"
    r"\b(?:map|drawing)\s+(?:no\.?|number|date)\b|\bdrawn\s+by\b|"
    r"\bscale\s*(?:[:=]|1\s*:)|\b(?:diagnosis|necropsy|histopathology)\b|"
    r"\b(?:appointed|entered\s+civic\s+service)\b"
    r")"
)
_NON_PUBLICATION_DATE_CONTEXT = re.compile(
    r"(?ix)(?:"
    r"\b(?:resigned|retired|appointed|born|died|effective)\b|"
    r"\b(?:capacity|statistics?|sampling|measurements?)\b|"
    r"\bfiscal\s+year\s+(?:ended|ending)\b|"
    r"\b(?:reading|lecture)\b|"
    r"\b(?:as\s+of|as\s+at|through|until|up\s+to|jusqu)\b"
    r")"
)
_CITED_WORK_CONTEXT = re.compile(
    r"(?ix)(?:"
    r"\b(?:following\s+)?extract\s+from\b|"
    r"\breference\s+paper\b|\bliterature\s+cited\b|"
    r"\b(?:bibliography|catalogue|catalog)\b|"
    r"\b(?:list|index)\s+of\s+(?:reports?|publications?|references?)\b"
    r")"
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
            if not MIN_PUBLICATION_YEAR <= self.year <= MAX_PUBLICATION_YEAR:
                raise ValueError(
                    "year must be within the collection's 1841--2013 span"
                )
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
        "title": 5_000,
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
    if not MIN_PUBLICATION_YEAR <= year <= MAX_PUBLICATION_YEAR:
        return None
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


def _copyright_year_matches(line: _Line) -> list[re.Match[str]]:
    """Years grammatically attached to a copyright imprint on this line."""
    if not _front(line, "copyright") or re.search(
        r"(?i)\bcopyright\s+(?:act|provisions?|restrictions?)\b", line.raw
    ):
        return []

    word = re.search(r"(?i)\b(?:copyright|copr\.?)\b|droits?\s+d", line.raw)
    if word and word.start() <= 30:
        attached: list[re.Match[str]] = []
        for year in _year_matches(line.raw):
            if year.start() < word.end() or year.start() - word.end() > 120:
                continue
            between = line.raw[word.end() : year.start()]
            if re.search(r"(?i)\b(?:published|material|report|article|notice)\b", between):
                continue
            if not re.search(r"[A-Za-z]", between) or re.search(
                r"(?i)\b(?:crown|queen|king|government|ministry|minister|"
                r"printer|canada|ontario)\b",
                between,
            ):
                attached.append(year)
        if attached:
            return attached

    symbol = line.raw.find("©")
    if symbol < 0 or line.raw[:symbol].strip(" \t.,;:()[]{}*-_"):
        return []
    years = _year_matches(line.raw)
    if not years:
        return []
    year = years[0]
    if year.start() - symbol > 60 or re.match(
        r"[\N{APOSTROPHE}\N{RIGHT SINGLE QUOTATION MARK}]s\b",
        line.raw[year.end() :],
        re.IGNORECASE,
    ):
        return []
    between = line.raw[symbol + 1 : year.start()]
    if not re.search(r"[A-Za-z]", between) or re.search(
            r"(?i)\b(?:crown|queen|king|government|ministry|minister|canada|ontario)\b",
            between,
        ):
        # A copyright belonging to an embedded logo, certification mark, map,
        # or photograph is not the document imprint.  Government/Crown labels
        # are strong enough to stand alone; other rightsholders need ordinary
        # colophon position very near the beginning of OCR.
        after = line.raw[year.end() :]
        government = bool(
            re.search(
                r"(?i)\b(?:crown|queen|king|government|ministry|minister|"
                r"printer|canada|ontario)\b",
                between + after,
            )
        )
        if government or line.position <= 4_000:
            return [year]
    return []


def _publication_year_matches(line: _Line) -> list[re.Match[str]]:
    """Years locally attached to a line-leading publication/colophon label."""
    anchor = _PUBLICATION.search(line.raw)
    if not anchor or not _front(line, "publication"):
        return []
    imprint = bool(
        re.search(
            r"(?i)(?:queen|king).?s\s+printer|imprimeur|minister\s+of\s+supply",
            anchor.group(0),
        )
    )
    attached: list[re.Match[str]] = []
    for year in _year_matches(line.raw):
        if year.start() < anchor.end() or year.start() - anchor.end() > 100:
            continue
        between = line.raw[anchor.end() : year.start()]
        after = line.raw[year.end() :]
        if re.match(
            r"(?i)^\s+(?:copies|reports?|articles?|brochures?|editions?|"
            r"impressions?|leaflets?|booklets?)\b",
            after,
        ):
            continue
        if re.search(
            r"(?i)\b(?:results?|copies|report|material|data|article|notice|"
            r"brochure|statistics?|figures?)\b",
            between,
        ):
            continue
        by_authority = bool(re.match(r"(?is)^\s+by\s+authority\s+of\b", between))
        has_month = bool(re.search(rf"(?i)\b(?:{_MONTH})\b", between))
        simple = bool(
            re.fullmatch(r"(?is)[\s,:;.-]*(?:(?:in|on|en)\s+)?", between)
        )
        if imprint or by_authority or has_month or simple:
            attached.append(year)
    return attached


def _revision_year_matches(line: _Line) -> list[re.Match[str]]:
    """Years attached to an explicit edition, revision, or printing date."""
    anchor = _REVISION.search(line.raw)
    if not anchor or re.search(
        r"(?i)^\s*revised\s+(?:statutes?|regulations?|act)\b", line.raw
    ):
        return []
    attached: list[re.Match[str]] = []
    for year in _year_matches(line.raw):
        if year.start() < anchor.end() or year.start() - anchor.end() > 70:
            continue
        between = line.raw[anchor.end() : year.start()]
        after = line.raw[year.end() :]
        if re.match(
            r"(?i)^\s+(?:copies|reports?|articles?|brochures?|editions?|"
            r"impressions?|leaflets?|booklets?)\b",
            after,
        ):
            continue
        if re.search(r"(?i)^\s+(?:of|for)\b", between) or re.search(
            r"(?i)\b(?:estimates?|results?|statistics?|data|reference\s+paper|"
            r"catalogue|catalog|bibliography)\b",
            between,
        ):
            continue
        if re.search(rf"(?i)\b(?:{_MONTH})\b", between) or re.fullmatch(
            r"(?is)[\s,:;.-]*(?:(?:to|in|on)\s+)?", between
        ):
            attached.append(year)
    return attached


def _extract_explicit(lines: list[_Line]) -> list[_Candidate]:
    out: list[_Candidate] = []
    for index, line in enumerate(lines):
        evidence = line.evidence
        if not evidence or len(evidence) > 280 or not _year_matches(line.raw):
            continue
        nearby_prefix = _exact_slice(lines, max(0, index - 3), index)
        if (
            _DIGITIZATION.search(line.raw)
            or _CITED_WORK_CONTEXT.search(nearby_prefix)
            or re.search(r"(?i)\bcopyright\s+act\b", line.raw)
        ):
            continue

        copyright_matches = _copyright_year_matches(line)
        revision_matches = _revision_year_matches(line)
        if revision_matches:
            remaining = len(line.source.text) - line.start
            closing_window = min(
                1_500,
                max(300, int(len(line.source.text) * 0.10)),
            )
            near_end = not line.source.physical_pages and remaining <= closing_window
            nearby = _exact_slice(
                lines,
                max(0, line.index - 8),
                min(len(lines) - 1, line.index + 8),
            )
            # A revision/printing line inside a bound volume dates that embedded
            # work, not the archive item. Accept it only in a real opening or a
            # tight closing-colophon window; a 12k-character tail proved broad
            # enough to swallow ordinary bodies in modest documents.
            body_form_context = bool(
                re.search(
                    r"(?i)\b(?:yes|no)\s*(?:[xX]|___+)?\b|\bquestionnaire\b|"
                    r"\brules?\s+and\s+regulations?\b",
                    nearby,
                )
            )
            if (
                not (_front(line, "publication") or near_end)
                or body_form_context
            ):
                revision_matches = []
        publication_matches = _publication_year_matches(line)
        if copyright_matches:
            matches = copyright_matches
            basis, confidence, revision = "copyright line", 0.96, False
        elif revision_matches:
            matches = revision_matches
            basis, confidence, revision = "publication line", 0.94, True
        elif publication_matches:
            matches = publication_matches
            basis, confidence, revision = "publication line", 0.94, False
        else:
            continue
        for match in matches:
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
        date_matches = [
            match for match in date_matches if _looks_like_front_date(line.raw, match)
        ]
        if not date_matches:
            continue
        first = max(0, index - 8)
        last = min(len(lines) - 1, index + 22)
        context = _exact_slice(lines, first, last)
        if (
            not _LETTER_ADDRESSEE.search(context)
            or not _LETTER_TRANSMITTAL.search(context)
            or _NOT_A_LETTER.search(line.raw)
        ):
            continue
        period_years = {
            int(match.group("year"))
            for context_line in lines[first : last + 1]
            if _ANNUAL.search(context_line.raw)
            or re.search(r"(?i)\b(?:fiscal|calendar)\s+year\b", context_line.raw)
            for match in _year_matches(context_line.raw)
        }
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
                confidence=0.82,
                tier=2,
                basis="covering letter",
                evidence=context,
                alternatives=tuple(
                    sorted(period_years - {int(year_match.group("year"))})
                ),
            )
            if found:
                out.append(found)
    return out


def _annual_year_matches(line: _Line) -> list[re.Match[str]]:
    """Years structurally tied to this document's reporting-period heading."""
    text = line.raw
    if len(line.evidence) > 320:
        return []
    reporting_title = _REPORTING_TITLE.search(text)
    if reporting_title and re.match(r"(?i)^\s*\d{4}\s+report\s+on\b", text):
        reporting_title = None
    annual = re.search(r"(?i)\b(?:annual\s+report|rapport\s+annuel)\b", text)
    ended = re.search(
        r"(?i)^\s*(?:financial\s+statements?\s+)?(?:report\s+)?"
        r"for\s+the\s+year\s+ended\b",
        text,
    )
    fiscal = re.search(
        r"(?i)^\s*fiscal\s+year\s+(?:ended|ending)\b",
        text,
    )
    if reporting_title:
        if reporting_title.start() > 35 or re.search(
            r"(?i)\b(?:supplements?|according\s+to|examination\s+of|"
            r"review\s+of|prior|previous|list\s+of)\b",
            text[: reporting_title.start()],
        ):
            return []
        anchor_start, anchor_end = reporting_title.span()
    elif annual:
        prefix = text[: annual.start()]
        if annual.start() > 80 or re.search(
            r"(?i)\b(?:copies?|discussion|review|summary|index|catalogue|"
            r"available|requested|mentions?|cites?|concerning|respecting|"
            r"examination|according|supplements?|previous|prior)\b",
            prefix,
        ):
            return []
        if _CITED_WORK_CONTEXT.search(prefix):
            return []
        anchor_start, anchor_end = annual.span()
    elif ended or fiscal:
        period = ended or fiscal
        assert period is not None
        anchor_start, anchor_end = period.span()
    else:
        return []

    return [
        match
        for match in _year_matches(text)
        if anchor_start - 18 <= match.start() <= anchor_end + 140
    ]


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
    opening = _exact_slice(lines, 0, min(len(lines) - 1, 80))
    document_is_event_record = bool(_NON_PUBLICATION_DOCUMENT.search(opening))
    for index, line in enumerate(lines):
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
        if _LIBRARY_STAMP_DATE.fullmatch(line.raw) or _WEEKDAY_DATE.match(line.raw):
            continue
        local_context = _exact_slice(
            lines,
            max(0, index - 8),
            min(len(lines) - 1, index + 8),
        )
        preceding_context = _exact_slice(lines, max(0, index - 3), index)
        if (
            _NOT_FRONT_MATTER_CONTEXT.search(local_context)
            or _NON_PUBLICATION_DATE_CONTEXT.search(preceding_context)
            or _CITED_WORK_CONTEXT.search(preceding_context)
        ):
            continue

        date_matches = list(_FULL_DATE.finditer(line.raw)) or list(
            _MONTH_YEAR.finditer(line.raw)
        )
        if _RANGE.search(line.raw) or len(_MONTH_YEAR.findall(line.raw)) > 1:
            # A span such as "January 1978 - October 1995" is almost always a
            # chart/coverage range, not a publication date.
            continue
        if not date_matches:
            standalone = (
                _STANDALONE_YEAR.match(line.raw) if line.source.physical_pages else None
            )
            date_matches = [standalone] if standalone else []
        if not date_matches:
            continue
        if document_is_event_record:
            continue

        date_matches = [
            match
            for match in date_matches
            if match
            and not re.search(
                r"(?i)\b(?:passed|ending|ended|approved|adopted|dated)\b",
                line.raw[: match.start()],
            )
            and _looks_like_front_date(line.raw, match)
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
    opening = _exact_slice(lines, 0, min(len(lines) - 1, 80))
    document_is_event_record = bool(_NON_PUBLICATION_DOCUMENT.search(opening))
    for index, line in enumerate(lines):
        if not _front(line, "annual") or document_is_event_record:
            continue
        nearby_prefix = _exact_slice(lines, max(0, index - 3), index)
        if _CITED_WORK_CONTEXT.search(nearby_prefix):
            continue
        year_matches = _annual_year_matches(line)
        if not year_matches:
            continue
        evidence = line.evidence
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

        for match in year_matches:
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
        # Projection labels often sit immediately above the TABLE heading.
        # Include that lead-in or a future scenario can masquerade as observed
        # data merely because its numeric grid starts on the next line.
        block = _exact_slice(lines, max(0, index - 8), index + len(window) - 1)
        if _FUTURE_TABLE.search(block) or re.search(
            r"(?i)\b(?:bibliography|references|literature\s+cited)\b", block
        ):
            continue

        matches: list[tuple[_Line, re.Match[str]]] = []
        numeric_rows = 0
        horizontal_years = False
        for line in window:
            raw_years = [
                match
                for match in _year_matches(line.raw)
                if not _reject_year_context(line.raw, match)
            ]
            distinct_line_years = {int(match.group("year")) for match in raw_years}
            stripped = line.raw.lstrip(" |()[]")
            starts_with_year = bool(
                raw_years and raw_years[0].start() <= len(line.raw) - len(stripped) + 2
            )
            tabular_spacing = "|" in line.raw or bool(re.search(r"\s{2,}", line.raw))
            prose_like = bool(
                len(re.findall(r"[A-Za-z]{2,}", line.raw)) > 10
                or re.search(r"[.!?](?:\s|$)", line.raw)
            )
            row_has_structure = bool(
                raw_years
                and (
                    (starts_with_year and not prose_like)
                    or (
                        len(distinct_line_years) >= 2
                        and tabular_spacing
                        and not prose_like
                    )
                    or (
                        tabular_spacing
                        and len(_NUMBER.findall(line.raw)) >= 2
                        and "," not in line.raw
                        and not prose_like
                    )
                )
            )
            line_years = raw_years if row_has_structure else []
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

    # A clean front dateline can be a sampling/map/edition date rather than the
    # document date.  A nearby, explicitly labelled reporting title many years
    # away is enough contradiction to abstain.  A one-year lag is normal for an
    # annual report and remains a defensible alternative instead of a conflict.
    if chosen.tier == 3:
        reporting_periods = [
            candidate for candidate in candidates if candidate.tier == 4
        ]
        if any(abs(candidate.year - chosen.year) > 1 for candidate in reporting_periods):
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


# --------------------------------------------------------------------------
# whether a value's year can be trusted
# --------------------------------------------------------------------------
#
# Everything above infers when a DOCUMENT was published. This asks a narrower
# question about a single VALUE: is the year we filed it under actually safe?
#
# The dispute ledger surfaced the problem without anyone looking for it.
# Brantford's 1969 report says "The average solids concentrations of 5.1% was
# less than the 1968 average of 5.3%", and both numbers were filed under 1969.
# A comparison sentence carries its own history, and taking the report's year
# for every value in it manufactures a change that did not happen. 27 of the 56
# contested measurements in the first ledger run are this shape.
#
# This detects the risk. It does NOT correct it, and the distinction was decided
# by trying the other way first. A rule that reassigned values to the nearest
# year moved 14 records and got several of them wrong in a new direction:
#
#   "5.1% was less than the 1968 average"      -- 5.1 is the report's own year
#   "an increase of 0.7 percent over 1967"     -- 0.7 is the increase, and the
#                                                 increase belongs to 1968
#   "the 1968 average of 5.3%"                 -- 5.3 really is 1968's
#
# Telling those apart needs to know whether the year modifies the value's own
# noun phrase or introduces a comparison, which is grammar rather than
# proximity. Guessing it silently would trade a known error for an invisible
# one, and an invisible wrong year turns a flat series into a trend. So the
# sentence is flagged and a person -- or the dispute ledger, which already shows
# both readings with their crops -- decides.

#: Words that mean the year is a point of comparison rather than the value's
#: own date. Their presence is what separates "over 1967 flows" from "the 1967
#: average".
_COMPARISON = re.compile(
    r"(?i)\b(over|than|versus|vs\.?|compared\s+(?:to|with)|against|"
    r"above|below|since|from|increase|decrease|higher|lower|more|less)\b")


@dataclass
class PeriodRisk:
    """Whether a value's filed year survives reading its own sentence."""

    period: str
    other_years: list[str] = field(default_factory=list)
    comparison: bool = False
    why: str = ""

    @property
    def safe(self) -> bool:
        return not self.other_years

    def to_dict(self) -> dict[str, Any]:
        return {"period": self.period, "safe": self.safe,
                "other_years": self.other_years,
                "comparison": self.comparison, "why": self.why}


def period_risk(quote: str, *, period: str = "") -> PeriodRisk:
    """Does this sentence mention a year other than the one we filed it under?

    A cheap, total check. Any sentence naming another year can carry a value
    belonging to that year, and every value taken from such a sentence deserves
    to be looked at rather than trusted.
    """
    text = str(quote or "")
    if not text:
        return PeriodRisk(period, why="no sentence to read")

    stated = str(period or "")[:4]
    years = sorted({m.group("year") for m in _YEAR.finditer(text)})
    others = [y for y in years if y != stated]
    if not others:
        return PeriodRisk(period, why="the sentence names no other year")

    comparison = bool(_COMPARISON.search(text))
    return PeriodRisk(
        period, other_years=others, comparison=comparison,
        why=(f"the sentence also names {', '.join(others)}"
             + (" in a comparison, so at least one value in it probably belongs "
                "to that year rather than to this report"
                if comparison else
                ", so a value here may belong to that year")),
    )
