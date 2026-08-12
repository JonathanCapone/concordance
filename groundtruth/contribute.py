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


def _value_in_quote(value: Any, quote: str) -> tuple[str, str]:
    """Does the number appear in the sentence it was supposedly read from?

    Digits are compared with punctuation stripped, because OCR renders "8.8" as
    "8. 8" and "53,549.66" with commas that come and go.

    Three outcomes, and the middle one matters:

      ok         the digits are there
      unchecked  the sentence has no digits at all, so the value was written in
                 words -- "just over three million gallons" really is where
                 3000000 comes from, and failing that would punish a correct read
      failed     the sentence has digits and none of them are this value, which
                 means the number and its evidence do not match
    """
    if value is None:
        return "unchecked", "no value to check"

    digits_in_quote = re.sub(r"[^0-9]", "", quote)
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

    if wanted in digits_in_quote:
        return "ok", ""

    # A rounded reading: "approximately 3,000,000" from "just over three million".
    # Leading digits still have to match something.
    if len(wanted) > 3 and wanted.rstrip("0") and wanted.rstrip("0") in digits_in_quote:
        return "ok", ""

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
    path = out_dir / f"contributed-{bundle['bundle_id']}.json"

    existing_keys: set[str] = set()
    for other in out_dir.glob("*.json"):
        try:
            payload = json.loads(other.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for r in payload.get("records", []) or []:
            if r.get("key"):
                existing_keys.add(r["key"])

    fresh = [r for r in bundle["records"] if r.get("key") not in existing_keys]
    path.write_text(json.dumps({
        "place": bundle.get("note") or "contributed",
        "contributor": bundle.get("contributor", "anonymous"),
        "bundle_id": bundle["bundle_id"],
        "verified": verdict.verified,
        "n_records": len(fresh),
        "records": fresh,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "written": str(path),
        "accepted": len(fresh),
        "duplicates_dropped": len(bundle["records"]) - len(fresh),
    }
