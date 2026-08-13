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
from . import numerals
from .models import record_key
from .places import scope_record_location

BUNDLE_VERSION = 1

#: How a table reading cites its source: the row and column headings that
#: locate the cell, rather than a sentence. Defined here and imported by
#: disputes, so the two paths cannot drift on what a cell citation looks like.
CELL_RE = re.compile(r"table\s+cell\s*\[\s*(.+?)\s*\]\s*$", re.I)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def bundle_id(records: list[dict[str, Any]]) -> str:
    """Content hash, so the same reading submitted twice is the same bundle."""
    # record_key, not r["key"]: the stored field is a snapshot from before
    # normalisation (see models.record_key). Reading it made every bundle of
    # key-less records hash to the SAME id -- the sha256 of an empty string --
    # so unrelated submissions collided on one filename and overwrote each other.
    keys = sorted(record_key(r) for r in records)
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
    supported: list[dict[str, Any]] = []
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
        # judged by the table rule -- the SAME one the dispute ledger uses,
        # imported rather than reimplemented.
        #
        # Without this, every record from the vision path failed here: 535 of
        # 535, because "table cell [January - Janvier / Fine vacuum / 2002]" is
        # not a sentence on the page and was never going to be. The ledger
        # verified those same records. So an instance published a reading and
        # then refused the identical reading when somebody pushed it, and the
        # work refused was precisely the contribution this project calls the
        # most valuable one -- a person with a graphics card reading the tables
        # nobody else can, once, for everyone.
        #
        # That is the third time two checks that are meant to be one check have
        # disagreed. The import is the fix for the class, not just the case.
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
            supported.append(record)
        elif state == "unchecked":
            # The SENTENCE is confirmed on the page; only the value could not be
            # judged. That is a real, if partial, piece of evidence, so it may be
            # kept -- unlike a record that cited nothing checkable at all.
            verdict.unchecked.append({**tag, "why": why})
            supported.append(record)
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

    # There used to be a "rounding" allowance here: strip the value's trailing
    # zeros and accept if the stub appears anywhere in the sentence's digits. It
    # was a hole big enough to drive the whole threat model through. 3,000,000
    # reduces to "3", so that value verified against ANY sentence containing a
    # 3 -- 62% of the quotes already in this repo accept the value 1,000,000 on
    # that rule. A contributor could invent a round flow, cite a real sentence
    # about something else, and the ledger would print "the value is in it as a
    # rounding of the figure the sentence states" underneath a scan that says no
    # such thing. Round numbers are exactly what this corpus is full of: flows,
    # populations, costs, capacities.
    #
    # It was worth almost nothing, which is the part worth recording. Across all
    # 962 published records only FOUR depended on it, and two of those are the
    # model guessing at destroyed OCR ("a total capacity of $0,000 cubic feet"
    # read as 25,000). Those four now show as unsupported in the ledger, which
    # is the honest place for them.
    #
    # The legitimate case it was reaching for -- "approximately 3,000,000" from
    # "just over three million" -- is handled properly below, by reading the
    # words.

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
    # The id names a FILE, and it arrives from whoever sent the bundle. A
    # sender who set it to "/../brantford" got `data/results/contributed-/../
    # brantford.json` -- which Windows resolves to a write OUTSIDE data/results,
    # over any .json the server process can reach, on a public unauthenticated
    # endpoint.
    #
    # The id is derived from the records anyway, so the sender's copy is at best
    # a cache of something recomputable. Recompute it and keep only characters
    # that cannot mean anything to a filesystem.
    claimed = str(bundle.get("bundle_id") or "")
    bid = claimed if re.fullmatch(r"[0-9a-f]{4,64}", claimed) else bundle_id(
        bundle.get("records") or [])
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
        # Resolve each stored record's place EXACTLY as Corpus.load does, by
        # calling the same function it calls. Identity has to be computed the
        # same way on the way in and on the way out.
        #
        # This used to do only the empty-place fallback, which covered the
        # thirty-one Brantford readings that store place=null. It missed the
        # other case: models put equipment and site labels in the place field
        # ("digesters", "Site 1", "Brantford Water Treatment Plant"), and the
        # loader resolves those to the municipality while the raw file keeps the
        # original. 231 of 5,241 records keyed differently in the two directions
        # and re-imported as new -- the same doubling-on-every-round-trip bug
        # this dedup was written to prevent, returning through a door nobody had
        # checked.
        #
        # Approximating another module's normalisation is what went wrong. Call
        # it instead.
        header_place = payload.get("place")
        for r in payload.get("records", []) or []:
            year = None
            try:
                year = int(str(r.get("period"))[:4])
            except (TypeError, ValueError):
                pass
            place, facility = scope_record_location(
                r.get("place"), header_place, r.get("facility"), year)
            existing_keys.add(record_key(dict(r, place=place, facility=facility)))

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
    source = verdict.supported if verdict.supported is not None else bundle["records"]

    fresh, seen = [], set()
    for r in source:
        k = record_key(r)
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
        # Measured against `source`, not the whole bundle. Counting the
        # difference from bundle["records"] reported 500 records the archive
        # REFUSED as "duplicates" -- a number that named the wrong reason and
        # made a rejected submission read like a redundant one.
        "duplicates_dropped": len(source) - len(fresh),
        "not_supported": len(bundle["records"]) - len(source),
    }
