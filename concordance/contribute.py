"""Accepting readings from people you have no reason to trust.

Most crowdsourced datasets need reputation, or duplicate-and-compare, or a
moderator. This one needs none of them, because of a property the extractor
already has: **every record carries a source citation and the exact page it came
from.** Prose records quote a sentence; experimental table records name their
cell headings.

So a prose contribution is checkable against the archive itself. Re-fetch the
page, confirm the cited sentence is really there, and confirm the complete number
is in that exact span. The contributor is never trusted and never needs to be —
archive.org is the referee, and it has no opinion about who submitted what.

The current table locator is weaker: headings can be confirmed independently,
but do not prove which number occupies their intersection. Those records are
preserved as experimental output and the public verifier abstains until it has
localized cell evidence.

That makes the check domain-independent, which is the part that matters. You can
accept a contribution about school examinations without knowing anything about
school examinations, because the question is always the same one.

What this CANNOT verify, and says so plainly:

  * that a reading was interpreted correctly -- "104 mg/1" really is on the page,
    but whether it is influent or effluent BOD is a judgement, and a wrong one
    passes this check
  * that a contribution is complete -- someone can submit the flattering half of
    a town's record and nothing here would notice
  * that the parameter vocabulary is right for a subject nobody has read before

For prose, verification catches several forms of fabrication. It does not catch
misreading, and pretending otherwise would be worse than having no check at all.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import threading
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .archive import Archive
from . import numerals
from .models import Provenance, Record, record_key
from .places import scope_record_dict

BUNDLE_VERSION = 1

#: How a table reading cites its source: the row and column headings that
#: locate the cell, rather than a sentence. Defined here and imported by
#: disputes, so the two paths cannot drift on what a cell citation looks like.
CELL_RE = re.compile(r"table\s+cell\s*\[\s*(.+?)\s*\]\s*$", re.I)

# ``merge_bundle`` is called by a threaded HTTP server. Deduplication is only
# true if discovering the records already on disk and publishing the new ones
# are one transaction: without this lock, two request threads can both scan the
# same old directory and then each publish their shared records. One lock for
# the process (rather than one per destination) also avoids a path-aliasing
# mistake turning two spellings of the same directory into two lock domains.
_MERGE_TRANSACTION_LOCK = threading.Lock()


@dataclass(frozen=True)
class _EvidenceToken:
    """One meaning-bearing token and its exact location in the page text."""

    value: str
    start: int
    end: int


# A number is one token even when OCR has inserted spaces after its decimal or
# thousands punctuation.  The punctuation itself is not optional: 312 and 3.12
# must never become the same evidence merely because a normalizer deleted dots.
_NUMBER_TEXT = (
    r"(?<![\w.])[+\-\N{MINUS SIGN}]?(?:"
    r"\d{1,3}(?:,\s*\d{3})+(?:\.\s*\d+)?|"
    r"\d+\.\s*\d+|\.\s*\d+|\d+"
    r")(?!\w|\.\s*\d)"
)
_EVIDENCE_TOKEN_RE = re.compile(
    rf"(?P<semantic>\+/-|<=|>=|[<>≤≥±%=£$€])|"
    rf"(?P<number>{_NUMBER_TEXT})|"
    r"(?P<word>[^\W\d_]+(?:[’'][^\W\d_]+)?)",
    re.UNICODE,
)


def _number_token(text: str) -> str:
    """Canonical numeric value without erasing its decimal structure."""

    cleaned = re.sub(r"\s+", "", text).replace("\N{MINUS SIGN}", "-")
    explicit_plus = cleaned.startswith("+")
    cleaned = cleaned.replace(",", "")
    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        return "number:" + cleaned
    if not number.is_finite():
        return "number:" + cleaned
    canonical = format(number.normalize(), "f")
    if "." in canonical:
        canonical = canonical.rstrip("0").rstrip(".")
    if canonical in {"-0", ""}:
        canonical = "0"
    if explicit_plus and not canonical.startswith("-"):
        canonical = "+" + canonical
    return "number:" + canonical


def _evidence_tokens(text: str) -> list[_EvidenceToken]:
    """Tokenize evidence while retaining numeric and comparison semantics.

    Sentence punctuation, line wrapping, and hyphenation remain tolerant.  A
    decimal point, numeric sign, comparison sign, percentage sign, or currency
    sign does not: deleting one of those can reverse or rescale the claim.
    """

    out: list[_EvidenceToken] = []
    for match in _EVIDENCE_TOKEN_RE.finditer(str(text or "")):
        kind = match.lastgroup
        raw = match.group()
        if kind == "number":
            value = _number_token(raw)
        elif kind == "semantic":
            value = {
                "≤": "<=", "≥": ">=", "+/-": "±",
            }.get(raw, raw)
            value = "semantic:" + value
        else:
            value = "word:" + raw.casefold().replace("’", "'")
        out.append(_EvidenceToken(value, match.start(), match.end()))
    return out


def _norm(text: str) -> str:
    """Comparable evidence form with explicit token boundaries.

    Kept for identity/comparison callers.  Page verification itself uses
    :func:`_match_evidence_span`, which can return the exact page characters
    that matched rather than trusting a submitter's normalized quote.
    """

    return "\x1f".join(token.value for token in _evidence_tokens(text))


def ground_condition(record: dict[str, Any]) -> dict[str, Any]:
    """Keep a record's `condition` only if its words are in the quoted sentence.

    The condition is the one field that changes a record's identity without
    being a fact about the measurement itself -- it is the circumstance the
    sentence attaches ("@ 55 ft head", "10 percent of the time"). If it could
    say anything, one true sentence resubmitted with N invented conditions
    would mint N distinct verified claims, because every other evidence check
    would still pass. So it is held to the same standard as the value: the
    words must be in the quote, in order, or they are removed.

    The RECORD survives either way. A wrong condition is an annotation failure,
    not a fabricated measurement, and stripping it collapses the identity back
    to the unconditioned record -- where dedup treats a poisoned twin as the
    duplicate it is. Fail closed on the annotation, never on the fact.

    Applied at every write boundary (extraction output, bundle merge, person
    submission), so stored data is grounded by construction and loaders never
    need to repeat the check.
    """
    condition = record.get("condition")
    if condition is None:
        return record
    text = str(condition) if isinstance(condition, str) else ""
    quote = str((record.get("provenance") or {}).get("source_text") or "")
    if condition_in_quote(text, quote):
        return record
    cleaned = dict(record)
    cleaned.pop("condition", None)
    return cleaned


def condition_in_quote(condition: str, quote: str) -> bool:
    """Are the condition's words inside the sentence, in order?

    Contiguous TOKEN containment, not substring: "each" must not pass on a
    sentence containing "beaches", which a join-then-substring check allows.
    """
    wanted = [t.value for t in _evidence_tokens(condition)]
    have = [t.value for t in _evidence_tokens(quote)]
    return bool(wanted) and any(
        have[i:i + len(wanted)] == wanted
        for i in range(len(have) - len(wanted) + 1))


def _match_evidence_span(quote: str, page_text: str) -> str | None:
    """Return the exact page span corresponding to ``quote``, if one exists.

    Matching is tolerant of ordinary punctuation and OCR line spacing but is a
    contiguous token match.  Crucially, numeric punctuation and semantic signs
    survive tokenization, so a submitted ``3.12`` cannot match page text ``312``
    and ``< 5`` cannot match ``> 5``.
    """

    wanted = _evidence_tokens(quote)
    page = _evidence_tokens(page_text)
    if not wanted or len(wanted) > len(page):
        return None
    values = [token.value for token in wanted]
    width = len(values)
    for start in range(len(page) - width + 1):
        if [token.value for token in page[start:start + width]] == values:
            first = page[start]
            last = page[start + width - 1]
            # A quote may be a sentence fragment, but it may not trim off an
            # immediately adjacent meaning-bearing sign. ``5`` is not a faithful
            # fragment of ``> 5`` or ``5%`` even though its numeric token occurs.
            if start and page[start - 1].value.startswith("semantic:"):
                between = str(page_text)[page[start - 1].end:first.start]
                if not between.strip():
                    continue
            if start + width < len(page) and page[start + width].value.startswith("semantic:"):
                between = str(page_text)[last.end:page[start + width].start]
                if not between.strip():
                    continue
            end = last.end
            while end < len(str(page_text)) and str(page_text)[end] in ".,;:!?":
                end += 1
            return str(page_text)[first.start:end]
    return None


def _has_prose_context(text: str) -> bool:
    """A prose citation must contain words, not merely a convenient number."""

    return any(token.value.startswith("word:") for token in _evidence_tokens(text))


_KINDS = {"observation", "standard", "design", "conclusion"}
_STREAMS = {"influent", "effluent", "ambient", "raw", "treated", "unknown"}
_PATHS = {"prose", "vision", "manual"}


def _is_json_value(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_value(item)
                   for key, item in value.items())
    return False


def record_problems(record: Any) -> list[str]:
    """Validate an untrusted record before archive or filesystem work.

    ``Record.problems`` remains the domain contract.  This wrapper first checks
    the JSON shapes needed to construct that model safely, then applies its
    existing semantic checks without changing the protected model module.
    """

    if not isinstance(record, dict):
        return ["record must be a JSON object"]
    problems: list[str] = []
    if not _is_json_value(record):
        problems.append("record contains a non-JSON or non-finite value")

    kind = record.get("kind")
    if kind not in _KINDS:
        problems.append("kind must be observation, standard, design, or conclusion")

    parameter = record.get("parameter")
    if not isinstance(parameter, str) or not parameter.strip():
        problems.append("parameter must be non-empty text")

    value = record.get("value")
    if value is not None and (isinstance(value, bool) or
                              not isinstance(value, (int, float)) or
                              not math.isfinite(float(value))):
        problems.append("value must be a finite number or null")
    if kind != "conclusion" and value is None:
        problems.append("only a conclusion may omit its numeric value")

    for field_name in ("unit", "place", "facility", "condition",
                       "comparability_note", "notes", "key"):
        field_value = record.get(field_name)
        if field_value is not None and not isinstance(field_value, str):
            problems.append(f"{field_name} must be text or null")
    condition = record.get("condition")
    if isinstance(condition, str) and len(condition) > 200:
        # It names a circumstance inside one sentence; a novel is an attack.
        problems.append("condition must be 200 characters or fewer")
    period = record.get("period")
    if (period is not None and
            (isinstance(period, bool) or not isinstance(period, (str, int)))):
        problems.append("period must be text, an integer year, or null")

    qualifier = record.get("qualifier")
    # The frozen corpus contains several honest domain extensions (frequency,
    # limit, difference, standard). Keep the untrusted boundary type-safe without
    # pretending the older Literal annotation is a complete future vocabulary.
    if qualifier is not None and not isinstance(qualifier, str):
        problems.append("qualifier must be text or null")
    stream = record.get("stream", "unknown")
    if stream not in _STREAMS:
        problems.append("stream is not recognized")

    confidence = record.get("confidence", 0.0)
    if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
            or not math.isfinite(float(confidence))
            or not 0.0 <= float(confidence) <= 1.0):
        problems.append("confidence must be a finite number from 0 to 1")

    raw = record.get("raw", {})
    if not isinstance(raw, dict):
        problems.append("raw must be a JSON object")

    provenance = record.get("provenance")
    if not isinstance(provenance, dict):
        problems.append("provenance must be a JSON object")
        provenance = {}
    identifier = provenance.get("identifier")
    if not isinstance(identifier, str) or not identifier.strip():
        problems.append("provenance identifier must be non-empty text")
    page = provenance.get("page")
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        problems.append("provenance page must be a positive integer")
    source_text = provenance.get("source_text")
    if not isinstance(source_text, str) or not source_text.strip():
        problems.append("provenance source_text must be non-empty text")
    extractor = provenance.get("extractor", "")
    if not isinstance(extractor, str):
        problems.append("provenance extractor must be text")
    path = provenance.get("path", "prose")
    if path not in _PATHS:
        problems.append("provenance path is not recognized")
    page_url = provenance.get("page_url")
    if page_url is not None and not isinstance(page_url, str):
        problems.append("provenance page_url must be text")

    if problems:
        return list(dict.fromkeys(problems))

    try:
        model = Record(
            kind=kind,
            parameter=parameter,
            value=value,
            unit=record.get("unit"),
            qualifier=qualifier,
            stream=stream,
            place=record.get("place"),
            period=(str(period) if isinstance(period, int) else period),
            facility=record.get("facility"),
            condition=record.get("condition"),
            confidence=float(confidence),
            provenance=Provenance(
                identifier=identifier,
                page=page,
                source_text=source_text,
                extractor=extractor,
                path=path,
            ),
            comparability_note=record.get("comparability_note"),
            notes=record.get("notes"),
            raw=raw,
        )
        problems.extend(model.problems())
    except (TypeError, ValueError, AttributeError) as exc:
        problems.append(f"record cannot be constructed: {str(exc)[:80]}")
    return list(dict.fromkeys(problems))


def public_record_key(record: dict[str, Any]) -> str:
    """Content identity with JSON numeric spelling canonicalized.

    Python/JSON may carry the same reading as ``1`` or ``1.0``; IEEE negative
    zero is equal to zero as a measurement.  The protected historical
    ``models.record_key`` stringifies values and therefore distinguishes those
    spellings.  Public import/dedup canonicalizes only finite numeric values,
    then delegates every other identity field to that shared contract.
    """

    value = record.get("value")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        if math.isfinite(numeric):
            canonical: int | float = 0 if numeric == 0 else (
                int(numeric) if numeric.is_integer() else numeric
            )
            if type(value) is not type(canonical) or value != canonical:
                record = dict(record, value=canonical)
    return record_key(record)


def bundle_id(records: list[dict[str, Any]]) -> str:
    """Content hash, so the same reading submitted twice is the same bundle."""
    # record_key, not r["key"]: the stored field is a snapshot from before
    # normalisation (see models.record_key). Reading it made every bundle of
    # key-less records hash to the SAME id -- the sha256 of an empty string --
    # so unrelated submissions collided on one filename and overwrote each other.
    keys = sorted(public_record_key(r) for r in records)
    return hashlib.sha256("|".join(keys).encode()).hexdigest()[:16]


@dataclass
class Verdict:
    """What the archive said about each record in a bundle.

    The distinction between `unchecked` and `unsupported` is the whole point of
    this class and it did not exist until an audit found what its absence cost.
    Both used to be "unchecked", and everything that was not `failed` was merged
    -- so a sender could keep ONE genuine record, append five hundred inventions
    with no provenance at all, and have the lot written into the library. The
    response even said "nothing was taken on trust".

      verified     the sentence is on the page and the value is in it
      unchecked    the sentence IS on the page; the value could not be judged
                   (a conclusion with no number, a figure written in words)
      unsupported  nothing was confirmed -- no quote, or the page could not be
                   fetched. Never merged, because nothing here is evidence.
      failed       the sentence is on the page and states a different number

    Only `verified` and `unchecked` are safe to keep, and `supported` carries
    exactly those records so the merge cannot re-derive the set and get it wrong.
    """

    total: int = 0
    verified: int = 0
    failed: list[dict[str, Any]] = field(default_factory=list)
    unchecked: list[dict[str, Any]] = field(default_factory=list)
    unsupported: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    #: Records the archive actually stands behind. None means "not computed by
    #: verify_bundle" -- only hand-built verdicts in tests -- and merge falls
    #: back to the whole bundle for those.
    supported: list[dict[str, Any]] | None = None

    @property
    def rate(self) -> float:
        return self.verified / self.total if self.total else 0.0

    @property
    def accepted(self) -> bool:
        """A bundle is accepted only if EVERY checkable record checks out.

        Not a threshold. One fabricated sentence in a submission means the
        submission was not produced the way it claims, and the honest response is
        to reject the lot rather than keep the parts that happened to pass.
        """
        return self.total > 0 and not self.failed and self.verified > 0

    def summary(self) -> str:
        if not self.total:
            return "empty bundle"
        head = (f"{self.verified}/{self.total} records verified against the scans"
                f" ({self.rate:.0%})")
        if self.failed:
            head += f" — {len(self.failed)} FAILED, bundle rejected"
        if self.unchecked:
            head += f" — {len(self.unchecked)} on the page but not judgeable"
        if self.unsupported:
            head += f" — {len(self.unsupported)} UNSUPPORTED, not merged"
        return head


def make_bundle(
    records: list[dict[str, Any]],
    *,
    contributor: str = "anonymous",
    note: str = "",
) -> dict[str, Any]:
    """Package extracted records for submission.

    `contributor` is a label, not a credential. Nothing here depends on who
    someone says they are, which is the point.
    """
    return {
        "bundle_version": BUNDLE_VERSION,
        "bundle_id": bundle_id(records),
        "contributor": contributor,
        "note": note,
        "n_records": len(records),
        "identifiers": sorted({(r.get("provenance") or {}).get("identifier", "")
                               for r in records} - {""}),
        "records": records,
    }


def verify_bundle(
    bundle: dict[str, Any],
    *,
    archive: Archive | None = None,
    sample: int | None = None,
) -> Verdict:
    """Check every prose record's quoted sentence against the page it claims.

    Locator-only table records are assessed by the shared table rule and remain
    unsupported unless independently localized cell evidence becomes available.

    `sample` checks only the first N records, for a fast pre-flight. A bundle
    accepted on a sample has not really been verified, and `accepted` still
    requires that nothing checked failed.
    """
    archive = archive or Archive()
    records = bundle.get("records") or []
    if sample:
        records = records[:sample]

    verdict = Verdict(total=len(records))
    supported: list[dict[str, Any]] = []
    pages: dict[str, dict[int, str]] = {}

    # Validate the complete untrusted shape before any of its provenance can
    # trigger archive work.  In particular, an observation with value=null is
    # not an "unchecked" conclusion: it is an invalid observation and can never
    # ride into a merge beside one genuine record.
    valid_records: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        problems = record_problems(record)
        if problems:
            tag = {"record": index + 1}
            if isinstance(record, dict):
                prov = record.get("provenance")
                prov = prov if isinstance(prov, dict) else {}
                tag.update({
                    "identifier": prov.get("identifier"),
                    "page": prov.get("page"),
                    "parameter": record.get("parameter"),
                    "value": record.get("value"),
                    "quote": str(prov.get("source_text") or "")[:120],
                })
            verdict.failed.append({**tag, "why": "invalid record: " + "; ".join(problems)})
        else:
            valid_records.append(record)

    for record in valid_records:
        prov = record.get("provenance") or {}
        ident = prov.get("identifier")
        page_no = prov.get("page")
        quote = prov.get("source_text") or ""
        tag = {
            "identifier": ident, "page": page_no,
            "parameter": record.get("parameter"), "value": record.get("value"),
            "quote": quote[:120],
        }

        if not (ident and page_no and quote):
            verdict.unsupported.append(
                {**tag, "why": "no page or no quoted sentence -- nothing to check"})
            continue

        if ident not in pages:
            try:
                pages[ident] = {p.page: p.text for p in archive.pages(ident)}
            except Exception as exc:  # noqa: BLE001
                verdict.errors.append(f"{ident}: {str(exc)[:90]}")
                pages[ident] = {}

        text = pages[ident].get(page_no, "")
        if not text:
            verdict.unsupported.append({**tag, "why": "page not retrievable"})
            continue

        # A table reading has headings where a sentence would be, so it is
        # judged by the SAME conservative table rule as the dispute ledger,
        # imported rather than reimplemented. Current locators cannot bind a
        # number to the headings' intersection, so the shared rule abstains.
        cell = CELL_RE.match(quote.strip())
        if cell:
            from .disputes import Claim, _check_cell   # local: disputes imports us

            standing = _check_cell(Claim(record=record), cell, text)
            if standing.verified:
                verdict.verified += 1
                supported.append(record)
            else:
                verdict.failed.append({**tag, "why": standing.why})
            continue

        if not _has_prose_context(quote):
            verdict.failed.append({
                **tag,
                "why": "prose evidence must include textual context, not only a number",
            })
            continue

        matched_evidence = _match_evidence_span(quote, text)
        if matched_evidence is None:
            verdict.failed.append({**tag, "why": "quoted sentence is not on that page"})
            continue

        # The quote is real. Now: is the VALUE actually in it?
        #
        # Without this, changing a number while keeping its true sentence passes
        # cleanly -- the most obvious way to poison a contribution, and the one a
        # sentence check alone cannot see.
        # Judge the value against the exact characters recovered from the page,
        # not against the sender's version of the quote.  Otherwise a sender can
        # insert a decimal into both quote and value and have punctuation-erasing
        # provenance matching launder 312 into 3.12.
        state, why = _value_in_quote(record.get("value"), matched_evidence)
        verified_record = dict(record)
        verified_record["provenance"] = dict(prov, source_text=matched_evidence.strip())
        if state == "ok":
            verdict.verified += 1
            supported.append(verified_record)
        elif state == "unchecked":
            # The SENTENCE is confirmed on the page; only the value could not be
            # judged. That is a real, if partial, piece of evidence, so it may be
            # kept -- unlike a record that cited nothing checkable at all.
            verdict.unchecked.append({**tag, "why": why})
            supported.append(verified_record)
        else:
            verdict.failed.append({**tag, "why": why})

    verdict.supported = supported
    return verdict


#: Letters 1960s OCR substitutes for digits INSIDE a numeral. Applied only to
#: runs that already contain a digit, so ordinary words are never turned into
#: numbers -- "Ill" stays a word, "I5" becomes 15.
_OCR_DIGIT = str.maketrans({"I": "1", "l": "1", "|": "1", "O": "0"})
_NUMERAL_RUN = re.compile(r"[0-9IlO|]*[0-9][0-9IlO|]*")


def _ocr_digits(text: str) -> str:
    """The sentence with letter-for-digit OCR damage undone inside numerals."""
    return _NUMERAL_RUN.sub(lambda m: m.group(0).translate(_OCR_DIGIT), text)


def _numbers_in(text: str, *, repair_ocr: bool = True) -> set[float]:
    """Every number the sentence states, read as numbers rather than as digits.

    Needed because a digit string cannot represent decimal formatting. The
    corpus writes "0.05" as ".05" and "0.5" as ".50", and comparing digit
    strings makes both of those disagree with the value they plainly state.
    Deliberately does NOT join numbers across whitespace: "8. 8" is already
    handled by the digit-substring test, and joining would invent numbers that
    the page does not contain.
    """
    t = _ocr_digits(text) if repair_ocr else text
    out: set[float] = set()
    scales = {
        "thousand": 1_000.0, "thousands": 1_000.0,
        "million": 1_000_000.0, "millions": 1_000_000.0,
        "billion": 1_000_000_000.0, "billions": 1_000_000_000.0,
    }
    for m in re.finditer(_NUMBER_TEXT, t):
        try:
            cleaned = re.sub(r"\s+", "", m.group()).replace("\N{MINUS SIGN}", "-")
            number = float(cleaned.replace(",", ""))
            out.add(number)
            scale = re.match(
                r"\s*(thousands?|millions?|billions?)\b", t[m.end():], re.I,
            )
            if scale:
                out.add(number * scales[scale.group(1).lower()])
        except (ValueError, OverflowError):
            pass
    return out


def _value_in_quote(value: Any, quote: str) -> tuple[str, str]:
    """Does the number appear in the sentence it was supposedly read from?

    Numbers are parsed as complete tokens. OCR spaces after decimal and thousands
    punctuation are tolerated, but the punctuation itself is never erased.

    Three outcomes, and the middle one matters:

      ok         the digits are there -- and `why` says HOW, because "the
                 sentence states it" and "the sentence states it once the
                 scanner's letter-for-digit damage is undone" are different
                 strengths of evidence and a reader should see which one applied
      unchecked  the sentence has no digits at all, so the value was written in
                 words -- "just over three million gallons" really is where
                 3000000 comes from, and failing that would punish a correct read
      failed     the sentence has digits and none of them are this value, which
                 means the number and its evidence do not match
    """
    if value is None:
        return "unchecked", "no value to check"

    digits_in_quote = re.sub(r"[^0-9]", "", _ocr_digits(quote))
    if not digits_in_quote:
        # No digits anywhere -- but the number may be spelled out. "Just over
        # three million gallons" is a measurement, and returning "unchecked"
        # here was the honest answer available before words could be read.
        if isinstance(value, (int, float)):
            spelled = numerals.states_value(quote, float(value))
            if spelled is not None:
                return "ok", f"the sentence states it in words ({spelled.phrase!r})"
        # A number was claimed and the sentence states no number at all -- not in
        # digits, not in words. That is not an unjudgeable case, it is a reading
        # with no source: the value was inferred from somewhere else and attached
        # to a sentence that does not carry it.
        #
        # This used to return "unchecked", which under the new merge rule would
        # have kept it. Records with NO value still return "unchecked" further up
        # and are kept, which is right -- a conclusion has no number to support.
        return "failed", (
            "the sentence states no number, in digits or in words, so it cannot "
            f"be where {value} came from")

    # Compare complete numeric tokens rather than digit substrings. Substring
    # matching accepts 12 inside 3120, 1 inside 10, and 5 inside 53,549.66 --
    # exactly the kind of fabricated or truncated value this check exists to
    # refuse. Numeric comparison also handles ".05" versus 0.05 and comma
    # formatting without weakening token boundaries.
    #
    # Eight of eleven Brantford refusals were this and the OCR substitution
    # above -- correct readings of "I5 feet deep", "3I per cent", ".21 ug/L" --
    # rejected by a check that was stricter than the archive it was checking.
    # That is the fifth time this project has built a control tighter than the
    # world and had it report a catastrophe.
    #
    # The three that remain refused are all genuinely wrong, and they are the
    # reason not to simply loosen this: a value guessed off unreadable OCR
    # ("3)Gl6,5^l'0"), a transposition (16,200,000 for 16,120,000), and a
    # number the model DERIVED -- 6.57 / 52.5% = 12.5 -- and reported as though
    # the page had stated it. That last one is the most interesting failure the
    # check catches, because the arithmetic is right and the reading is still
    # false.
    if isinstance(value, (int, float)):
        numeric_value = float(value)
        # The empty explanation is reserved for the strongest case: the
        # canonical number itself appears as a complete token in the original
        # sentence. Commas may format thousands but cannot remove boundaries.
        canonical = repr(numeric_value)
        if canonical.endswith(".0"):
            canonical = canonical[:-2]
        direct = re.sub(r"(?<=\d),(?=\d)", "", quote)
        if re.search(rf"(?<![\d.+-]){re.escape(canonical)}(?![\d.])", direct):
            return "ok", ""
        if numeric_value in _numbers_in(quote, repair_ocr=False):
            return "ok", "reading the sentence's numbers as numbers, not as digits"
        if numeric_value in _numbers_in(quote):
            return "ok", "once OCR letter-for-digit damage is undone"

    # The page may have written the number out in words. numerals.states_value
    # is deliberately the narrow door: it requires a magnitude word, a trailing
    # unit, or a value too large to be an article, so "one of the plants was
    # closed" cannot be used to support the value 1.
    if isinstance(value, (int, float)):
        spelled = numerals.states_value(quote, float(value))
        if spelled is not None:
            return "ok", f"the sentence states it in words ({spelled.phrase!r})"

    return "failed", (
        f"the value {value} does not appear in the sentence it cites "
        f"(sentence digits: {digits_in_quote[:40]})"
    )


def _atomic_create(path: Path, content: bytes) -> None:
    """Publish complete bytes at a new path, never replacing an old file.

    The temporary file is in the destination directory, so the hard-link step
    is same-filesystem and atomic. Readers see either no destination or the
    complete JSON. ``os.link`` has create-new semantics on both Windows and
    POSIX: if another writer already claimed the name, it raises rather than
    replacing accepted data.
    """
    fd, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            # A different process can race this process-wide lock. Refusing the
            # write is conservative: a retry will rescan the newly landed file,
            # while replacing it here would destroy already accepted records.
            raise RuntimeError(
                f"contribution destination appeared during merge: {path.name}; retry"
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def _collision_safe_path(base: Path, content: bytes) -> Path:
    """Choose a free deterministic alternative without touching ``base``.

    A truncated content hash is a useful filename, not proof that an occupied
    file contains this payload. A collision can also occur when an earlier
    verification accepted only part of the same original bundle. Preserve the
    existing file and place the newly accepted subset beside it.
    """
    if not base.exists():
        return base
    tag = hashlib.sha256(content).hexdigest()[:16]
    candidate = base.with_name(f"{base.stem}-{tag}{base.suffix}")
    serial = 2
    while candidate.exists():
        candidate = base.with_name(f"{base.stem}-{tag}-{serial}{base.suffix}")
        serial += 1
    return candidate


def merge_bundle(
    bundle: dict[str, Any],
    into: str | Path = "data/results",
    *,
    verdict: Verdict | None = None,
) -> dict[str, Any]:
    """Merge a verified bundle as one process-wide disk transaction."""
    with _MERGE_TRANSACTION_LOCK:
        return _merge_bundle_transaction(bundle, into, verdict=verdict)


def _merge_bundle_transaction(
    bundle: dict[str, Any],
    into: str | Path = "data/results",
    *,
    verdict: Verdict | None = None,
) -> dict[str, Any]:
    """Merge an ACCEPTED bundle into the local dataset.

    Refuses anything that has not passed verification. Deduplicates on the record
    key, so the same reading submitted by two people lands once and neither
    contributor's copy is privileged. The caller holds
    ``_MERGE_TRANSACTION_LOCK`` for this entire scan/deduplicate/write sequence.
    """
    if verdict is None or not verdict.accepted:
        raise ValueError("bundle has not been verified, or verification failed")

    source = verdict.supported if verdict.supported is not None else bundle["records"]
    invalid = [
        (index, record_problems(record))
        for index, record in enumerate(source, start=1)
        if record_problems(record)
    ]
    if invalid:
        index, problems = invalid[0]
        raise ValueError(
            f"supported record {index} is invalid: {'; '.join(problems)}"
        )

    out_dir = Path(into)
    out_dir.mkdir(parents=True, exist_ok=True)

    # The id is derived from the records. The sender's copy is never authority:
    # even a syntactically valid hex string can deliberately name an earlier
    # contribution and make a later write replace that file. Missing, malformed
    # and plausible-looking claimed ids are therefore handled identically.
    #
    # This is the second family of bug this project keeps producing: an
    # identity treated as given rather than as something derivable from the
    # content it identifies.
    # The id names a FILE, and it arrives from whoever sent the bundle. A
    # sender who set it to "/../brantford" got `data/results/contributed-/../
    # brantford.json` -- which Windows resolves to a write OUTSIDE data/results,
    # over any .json the server process can reach, on a public unauthenticated
    # endpoint.
    #
    # Recompute it unconditionally. ``bundle_id`` returns lowercase hex from a
    # SHA-256 of canonical record keys, so the resulting name cannot traverse a
    # filesystem and two different ordinary bundles cannot choose one another's
    # destination.
    bid = bundle_id(bundle.get("records") or [])
    path = out_dir / f"contributed-{bid}.json"
    if path.resolve().parent != out_dir.resolve():
        raise ValueError("bundle id does not name a file inside the results directory")

    # Recomputed on BOTH sides, never read from the stored field. See
    # models.record_key: the `key` written into a results file is a snapshot
    # from before later normalisation, so comparing a live key against a stored
    # one never matches and every import re-adds everything.
    existing_keys: set[str] = set()
    for other in out_dir.glob("*.json"):
        try:
            payload = json.loads(other.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        # Deduplicate only against files the public Corpus itself loads. A
        # benchmark/report may contain example `records` but, without the
        # extraction shape's top-level `place` key, those records are not part of
        # the library and must not suppress a legitimate contribution.
        if not isinstance(payload, dict) or "place" not in payload:
            continue
        # Resolve each stored record's place EXACTLY as Corpus.load does, by
        # calling the same function it calls. Identity has to be computed the
        # same way on the way in and on the way out.
        #
        # This used to do only the empty-place fallback, which covered the
        # thirty-one Brantford readings that store place=null. It missed the
        # other case: models put equipment and site labels in the place field
        # ("digesters", "Site 1", "Brantford Water Treatment Plant"), and the
        # loader resolves those to the municipality while the raw file keeps the
        # original. Those records once keyed differently in the two directions
        # and re-imported as new -- the same doubling-on-every-round-trip bug
        # this dedup was written to prevent, returning through a door nobody had
        # checked.
        #
        # Approximating another module's normalisation is what went wrong. Call
        # it instead.
        header_place = payload.get("place")
        for r in payload.get("records", []) or []:
            existing_keys.add(public_record_key(scope_record_dict(r, header_place)))

    # Merge ONLY what the archive stood behind. This used to iterate the whole
    # bundle, so every record that was not outright FAILED rode in -- including
    # records that cited no page, and records whose page archive.org happened not
    # to serve that minute. One genuine reading was enough to carry an unlimited
    # number of inventions, and the next instance to pull this library would
    # re-publish them.
    #
    # verify_bundle computes the set; it is not re-derived here, because a merge
    # that reconstructs the verifier's judgement is a second implementation of
    # the check and this project has already been bitten by having two.
    fresh, seen = [], set()
    for raw_record in source:
        # A bundle exported from a result file has already passed through the
        # same helper in ``load_claims``. Applying it again is idempotent and
        # also keeps direct bundle callers on the canonical identity path.
        #
        # Grounding comes FIRST, before identity: a condition the quote does
        # not contain is stripped here, so the poisoned twin's key collapses
        # to the true record's key and the dedup below treats it as the
        # duplicate it is.
        r = scope_record_dict(ground_condition(raw_record), None)
        k = public_record_key(r)
        # Also dedup WITHIN the bundle. A sender who concatenated two exports
        # would otherwise land the same reading twice in one file, where the
        # next import would see it as one already-present record and one new.
        if k in existing_keys or k in seen:
            continue
        seen.add(k)
        fresh.append(r)
    if not fresh:
        # Nothing new -- so write NOTHING. The file is named by the bundle's
        # content hash, which means a replay of the same bundle targets the file
        # the first send created. The dedup scan then finds every record already
        # on disk (in that very file), leaves `fresh` empty, and the write
        # replaced a good file with an empty one.
        #
        # Re-sending a bundle is not an error and not an attack; it is what
        # happens when a push times out and somebody tries again. An add-only
        # endpoint that deletes on retry is the worst possible shape for it.
        return {
            "written": None,
            "accepted": 0,
            "duplicates_dropped": len(source),
            "not_supported": len(bundle["records"]) - len(source),
        }

    document = {
        # NOT the note. Corpus.load treats this field as the place any record
        # lacking one inherits, so putting a free-text note here stamped every
        # placeless imported reading with a sentence -- "readings from Fergus,
        # checked by hand" would have become a town. The note is kept, under its
        # own name, where nothing reads it as data.
        "place": "",
        "note": bundle.get("note") or "",
        "contributor": bundle.get("contributor", "anonymous"),
        "bundle_id": bid,
        "verified": verdict.verified,
        "n_records": len(fresh),
        "records": fresh,
    }
    encoded = json.dumps(document, indent=2, ensure_ascii=False).encode("utf-8")
    path = _collision_safe_path(path, encoded)
    _atomic_create(path, encoded)

    return {
        "written": str(path),
        "accepted": len(fresh),
        # Measured against `source`, not the whole bundle. Counting the
        # difference from bundle["records"] reported 500 records the archive
        # REFUSED as "duplicates" -- a number that named the wrong reason and
        # made a rejected submission read like a redundant one.
        "duplicates_dropped": len(source) - len(fresh),
        "not_supported": len(bundle["records"]) - len(source),
    }
