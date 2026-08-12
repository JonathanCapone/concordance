"""Accepting readings from people you have no reason to trust.

Most crowdsourced datasets need reputation, or duplicate-and-compare, or a
moderator. This one needs none of them, because of a property the extractor
already has: **every record carries the exact sentence it was read from, and the
page that sentence is on.**

So a contribution is checkable against the archive itself. Re-fetch the page,
confirm the sentence is really there, confirm the number is really in it. The
contributor is never trusted and never needs to be — archive.org is the referee,
and it has no opinion about who submitted what.

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

Verification catches fabrication. It does not catch misreading, and pretending
otherwise would be worse than having no check at all.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .archive import Archive
from .models import record_key

BUNDLE_VERSION = 1


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def bundle_id(records: list[dict[str, Any]]) -> str:
    """Content hash, so the same reading submitted twice is the same bundle."""
    keys = sorted(r.get("key", "") for r in records)
    return hashlib.sha256("|".join(keys).encode()).hexdigest()[:16]


@dataclass
class Verdict:
    total: int = 0
    verified: int = 0
    failed: list[dict[str, Any]] = field(default_factory=list)
    unchecked: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

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
            head += f" — {len(self.unchecked)} could not be checked"
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
    """Check every record's quoted sentence against the page it claims.

    `sample` checks only the first N records, for a fast pre-flight. A bundle
    accepted on a sample has not really been verified, and `accepted` still
    requires that nothing checked failed.
    """
    archive = archive or Archive()
    records = bundle.get("records") or []
    if sample:
        records = records[:sample]

    verdict = Verdict(total=len(records))
    pages: dict[str, dict[int, str]] = {}

    for record in records:
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
            verdict.unchecked.append({**tag, "why": "no page or no quoted sentence"})
            continue

        if ident not in pages:
            try:
                pages[ident] = {p.page: p.text for p in archive.pages(ident)}
            except Exception as exc:  # noqa: BLE001
                verdict.errors.append(f"{ident}: {str(exc)[:90]}")
                pages[ident] = {}

        text = pages[ident].get(page_no, "")
        if not text:
            verdict.unchecked.append({**tag, "why": "page not retrievable"})
            continue

        if _norm(quote) not in _norm(text):
            verdict.failed.append({**tag, "why": "quoted sentence is not on that page"})
            continue

        # The quote is real. Now: is the VALUE actually in it?
        #
        # Without this, changing a number while keeping its true sentence passes
        # cleanly -- the most obvious way to poison a contribution, and the one a
        # sentence check alone cannot see.
        state, why = _value_in_quote(record.get("value"), quote)
        if state == "ok":
            verdict.verified += 1
        elif state == "unchecked":
            verdict.unchecked.append({**tag, "why": why})
        else:
            verdict.failed.append({**tag, "why": why})

    return verdict


#: Letters 1960s OCR substitutes for digits INSIDE a numeral. Applied only to
#: runs that already contain a digit, so ordinary words are never turned into
#: numbers -- "Ill" stays a word, "I5" becomes 15.
_OCR_DIGIT = str.maketrans({"I": "1", "l": "1", "|": "1", "O": "0"})
_NUMERAL_RUN = re.compile(r"[0-9IlO|]*[0-9][0-9IlO|]*")


def _ocr_digits(text: str) -> str:
    """The sentence with letter-for-digit OCR damage undone inside numerals."""
    return _NUMERAL_RUN.sub(lambda m: m.group(0).translate(_OCR_DIGIT), text)


def _numbers_in(text: str) -> set[float]:
    """Every number the sentence states, read as numbers rather than as digits.

    Needed because a digit string cannot represent decimal formatting. The
    corpus writes "0.05" as ".05" and "0.5" as ".50", and comparing digit
    strings makes both of those disagree with the value they plainly state.
    Deliberately does NOT join numbers across whitespace: "8. 8" is already
    handled by the digit-substring test, and joining would invent numbers that
    the page does not contain.
    """
    t = re.sub(r"(?<=\d),(?=\d)", "", _ocr_digits(text))
    out: set[float] = set()
    for m in re.finditer(r"\d*\.\d+|\d+", t):
        try:
            out.add(float(m.group()))
        except ValueError:
            pass
    return out


def _value_in_quote(value: Any, quote: str) -> tuple[str, str]:
    """Does the number appear in the sentence it was supposedly read from?

    Digits are compared with punctuation stripped, because OCR renders "8.8" as
    "8. 8" and "53,549.66" with commas that come and go.

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

    literal = re.sub(r"[^0-9]", "", quote)
    digits_in_quote = re.sub(r"[^0-9]", "", _ocr_digits(quote))
    if not digits_in_quote:
        return "unchecked", "value is written in words, not digits"

    # repr(), not "%g". The g format rounds to six significant figures, so an
    # operating cost of 53549.66 became "53549.7" and stopped matching the very
    # sentence it came from -- rejecting an honest contribution for being
    # accurate. A trailing ".0" on whole numbers is stripped instead.
    text = repr(float(value)) if isinstance(value, (int, float)) else str(value)
    if text.endswith(".0"):
        text = text[:-2]
    wanted = re.sub(r"[^0-9]", "", text)
    if not wanted:
        return "unchecked", "value has no digits"

    if wanted in literal:
        return "ok", ""
    if wanted in digits_in_quote:
        return "ok", "once OCR letter-for-digit damage is undone"

    # A rounded reading: "approximately 3,000,000" from "just over three million".
    # Leading digits still have to match something.
    trimmed = wanted.rstrip("0")
    if len(wanted) > 3 and trimmed and trimmed in digits_in_quote:
        return "ok", "as a rounding of the figure the sentence states"

    # Last, compare as numbers rather than as digit strings, which is the only
    # way ".05 mg/L" can be seen to state 0.05.
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
    if isinstance(value, (int, float)) and float(value) in _numbers_in(quote):
        return "ok", "reading the sentence's numbers as numbers, not as digits"

    return "failed", (
        f"the value {value} does not appear in the sentence it cites "
        f"(sentence digits: {digits_in_quote[:40]})"
    )


def merge_bundle(
    bundle: dict[str, Any],
    into: str | Path = "data/results",
    *,
    verdict: Verdict | None = None,
) -> dict[str, Any]:
    """Merge an ACCEPTED bundle into the local dataset.

    Refuses anything that has not passed verification. Deduplicates on the record
    key, so the same reading submitted by two people lands once and neither
    contributor's copy is privileged.
    """
    if verdict is None or not verdict.accepted:
        raise ValueError("bundle has not been verified, or verification failed")

    out_dir = Path(into)
    out_dir.mkdir(parents=True, exist_ok=True)

    # The id is derived from the records, so a bundle that arrives without one
    # is not malformed -- it is merely incomplete, and the missing field can be
    # recomputed from the thing it names. Indexing it directly raised KeyError
    # inside a live request handler, which turned somebody else's slightly
    # unusual JSON into a 500 with no explanation at either end.
    #
    # This is the second family of bug this project keeps producing: an
    # identity treated as given rather than as something derivable from the
    # content it identifies.
    bid = bundle.get("bundle_id") or bundle_id(bundle.get("records") or [])
    path = out_dir / f"contributed-{bid}.json"

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
        # A record with no place of its own inherits the file's, exactly as
        # Corpus.load does -- so identity is computed the same way on the way in
        # and on the way out. Thirty-one Brantford readings store place=null and
        # load as "Brantford", and without this they key differently in the two
        # directions and re-import as new.
        header_place = payload.get("place")
        for r in payload.get("records", []) or []:
            if not r.get("place") and header_place:
                r = dict(r, place=header_place)
            existing_keys.add(record_key(r))

    fresh, seen = [], set()
    for r in bundle["records"]:
        k = record_key(r)
        # Also dedup WITHIN the bundle. A sender who concatenated two exports
        # would otherwise land the same reading twice in one file, where the
        # next import would see it as one already-present record and one new.
        if k in existing_keys or k in seen:
            continue
        seen.add(k)
        fresh.append(r)
    path.write_text(json.dumps({
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
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "written": str(path),
        "accepted": len(fresh),
        "duplicates_dropped": len(bundle["records"]) - len(fresh),
    }
