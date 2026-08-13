"""Path B: reading the tables that OCR destroyed.

The prose path works because the 2013-era OCR captured sentences well. It
captured tables terribly. A provincial summary table comes back as:

    9 /zLA' y 1? in" y 1'\\ Vnlump 41 Q sailor

Nothing can be recovered from that string. But the string is not the data -- the
scan is, and it is still there, at 1500 pixels wide, perfectly legible to a human
and now to a model.

**This is the part of the project that was impossible until recently.** The
tables were never lost. They were merely unreadable by the tools that existed
when the pages were scanned. Pointing a vision model at the page image rather
than at the OCR of the page image recovers data that has been sitting in public
and inaccessible for a decade.

The same two guards as the prose path apply, with one change forced by the
medium: a vision model cannot quote a source sentence from a table, because a
table has no sentences. Instead it must report the row and column labels it read
the value under, which serves the same purpose -- a human can find the cell on
the page in seconds and disagree.
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Any

from .extract import _parse_json_array, _to_float
from .models import PageText, Provenance, Record

DEFAULT_VISION_MODEL = "llava:latest"


@dataclass
class OllamaVisionClient:
    """Local vision model. Keeps the vision path keyless like everything else."""

    model: str = DEFAULT_VISION_MODEL
    base_url: str = "http://localhost:11434"
    timeout: float = 900.0
    think: bool = False

    @property
    def name(self) -> str:
        return f"ollama-vision:{self.model}"

    def read_image(self, system: str, prompt: str, image: bytes) -> str:
        payload = json.dumps({
            "model": self.model,
            "system": system,
            "prompt": prompt,
            "images": [base64.b64encode(image).decode()],
            "stream": False,
            "think": self.think,
            "options": {"temperature": 0.0, "num_predict": 3000},
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode()).get("response", "")


@dataclass
class AnthropicVisionClient:
    """Optional and markedly more capable on degraded scans. Never required."""

    model: str = "claude-sonnet-5"
    api_key: str | None = None
    max_tokens: int = 4096
    timeout: float = 300.0

    @property
    def name(self) -> str:
        return f"anthropic-vision:{self.model}"

    def read_image(self, system: str, prompt: str, image: bytes) -> str:
        key = self.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("no ANTHROPIC_API_KEY; use OllamaVisionClient instead")
        payload = json.dumps({
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": 0,
            "system": system,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/jpeg",
                        "data": base64.b64encode(image).decode(),
                    }},
                    {"type": "text", "text": prompt},
                ],
            }],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode())
        return "".join(b.get("text", "") for b in body.get("content", []))


SYSTEM = """\
You read tables from scanned Canadian government reports, often sixty years old,
printed on typewriters and scanned imperfectly.

Return ONLY a JSON array. No prose, no markdown fence. One element per data cell
that carries a measurement:

{
  "kind":       "observation" | "standard" | "design" | "conclusion",
  "parameter":  what the row or column says was measured,
  "value":      the number in the cell,
  "unit":       the unit, taken from the column heading or table caption if the
                cell itself does not repeat it,
  "qualifier":  "average"|"maximum"|"minimum"|"total"|"percent"|"count"|null,
  "stream":     "influent"|"effluent"|"ambient"|"raw"|"treated"|"unknown",
  "period":     the year or month this row refers to, if the table says,
  "confidence": 0.0 to 1.0 -- lower it when the print is faint or a digit is unclear,
  "row_label":  the row heading exactly as printed,
  "column_label": the column heading exactly as printed
}

Rules:
- row_label and column_label are how a reader finds the cell again. Always give
  both if the table has both. Copy them as printed; do not tidy them.
- If a digit is genuinely unreadable, leave that cell out. Do not guess a number.
  A missing value is recoverable; an invented one is not.
- Units usually live in the column heading, not the cell. Carry them down.
- A value under a heading like DESIGN or CAPACITY is "design", not "observation".
- If the page has no table, or the table has no measurements, return [].
"""

PROMPT = """\
Document: {title}
Publisher: {publisher}
Year: {year}
Page: {page}

Read every measurement in the table(s) on this page. Return the JSON array."""


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _label_on_page(label: str, page_text: str) -> bool:
    """Does a claimed row/column label actually appear on the page?

    Deliberately lenient about how much of the label matches, because OCR
    mangles headings too -- but a label that shares no substantial token with
    anything on the page is a fabrication, not a transcription.
    """
    page = _norm(page_text)
    if not page:
        return True  # nothing to check against; fall back to trusting the model
    whole = _norm(label)
    if whole and whole in page:
        return True
    tokens = [t for t in re.split(r"\W+", label.lower()) if len(t) >= 4]
    if tokens:
        return any(_norm(t) in page for t in tokens)

    # Short-token labels. A census column heading reads "CT - SR 135.03", and
    # the OCR of that header row runs "CT - SR CT - SR CT - SR ... 135.02
    # 135.03 136.01" -- the words and their numbers separated. The label is
    # therefore nowhere on the page as a contiguous string even though every
    # part of it is, and demanding the whole string rejected all 25 records on
    # a Statistics Canada page whose values were entirely correct.
    #
    # So for these, every part must be present somewhere rather than the whole
    # appearing intact. That is weaker, and it is the right kind of weaker: a
    # fabricated heading still has to be assembled from fragments the page
    # actually contains.
    parts = [t for t in re.split(r"\W+", label.lower()) if t]
    if not parts:
        return bool(whole) and whole in page
    return all(_norm(t) in page for t in parts)


def _page_can_referee(candidates: list[dict[str, Any]], page_text: str) -> bool:
    """Has this page's OCR proved it can confirm a heading at all?

    Self-calibrating, and deliberately so. A page whose text layer finds at
    least one of the headings the model claims has demonstrated that it works,
    which makes a heading it cannot find meaningful evidence against that
    heading. A page that finds none of them has demonstrated nothing, and its
    silence says more about the scanner than about the model.

    The alternative -- a minimum character count -- was tried and is too blunt.
    The phosphorus plot page that caught a vision model inventing "Phosphorus /
    Month" carries about 150 characters of OCR, and the Georgian Bay table page
    that was wrongly emptied carries about 1,000, so no cutoff separates them.
    What separates them is that the plot page can find "Phosphorus" and the
    table page can find nothing.
    """
    if not page_text.strip():
        return False
    for c in candidates:
        if not isinstance(c, dict):
            continue
        for key in ("row_label", "column_label"):
            label = str(c.get(key) or "").strip()
            if label and _label_on_page(label, page_text):
                return True
    return False


@dataclass
class VisionResult:
    records: list[Record]
    rejected: list[dict[str, Any]]
    raw_response: str

    @property
    def kept(self) -> int:
        return len(self.records)


def extract_table(
    page: PageText,
    image: bytes,
    *,
    client: Any = None,
    title: str = "",
    publisher: str = "",
    year: str = "",
) -> VisionResult:
    """Read one page image and return typed records.

    Provenance differs from the prose path by necessity. A table has no
    sentences, so `source_text` records the row and column labels the model read
    the value under. That is still enough for a human to find the cell on the
    scan and disagree with it, which is the property that matters.
    """
    client = client or OllamaVisionClient()
    raw = client.read_image(
        SYSTEM,
        PROMPT.format(
            title=title or "(unknown)", publisher=publisher or "(unknown)",
            year=year or "(unknown)", page=page.page,
        ),
        image,
    )
    candidates = _parse_json_array(raw)

    records: list[Record] = []
    rejected: list[dict[str, Any]] = []

    for c in candidates:
        if not isinstance(c, dict):
            continue
        kind = str(c.get("kind") or "").strip().lower()
        parameter = str(c.get("parameter") or "").strip()
        row = str(c.get("row_label") or "").strip()
        col = str(c.get("column_label") or "").strip()

        if kind not in ("observation", "standard", "design", "conclusion"):
            rejected.append({"why": f"unknown kind {kind!r}", "candidate": c})
            continue
        if not parameter:
            rejected.append({"why": "empty parameter", "candidate": c})
            continue
        if not row and not col:
            # The prose path verifies a quoted sentence against the page. Here the
            # equivalent check is that the model can say WHERE in the table it
            # looked. A cell with no coordinates cannot be checked by anyone.
            rejected.append({"why": "no row or column label -- cell is not locatable", "candidate": c})
            continue

        # ...and that the labels are REAL, not merely present.
        #
        # Requiring labels to exist is not enough. Run against a phosphorus
        # probability plot -- an axis of "percentage of samples equal to or less
        # than" -- a local vision model returned five values labelled
        # "Phosphorus / Month". The page has no monthly columns at all. The
        # structure was invented wholesale, and every fabricated record carried
        # labels and so passed the locatability check.
        #
        # OCR destroyed the table VALUES on these pages but usually preserved the
        # HEADINGS, which are set in larger and cleaner type. So the surviving
        # OCR text is exactly the right thing to check labels against, and it
        # costs one substring search.
        # ...but only on a page whose text layer can referee at all.
        #
        # The premise above -- that headings survive in cleaner type -- holds on
        # a page whose OCR is merely damaged and fails completely on one where it
        # was destroyed. Georgian Bay Ship Canal, 1909: a full table page reduced
        # to 1,068 characters, every one of its 30 records rejected for headings
        # that are simply not in the text layer. That is the exact circumstance
        # the vision path exists for, so a check that fires hardest there is
        # inverted -- strictest where it can judge least.
        #
        # A character threshold was the first attempt and it was too blunt: the
        # phosphorus plot page that caught llava's invented "Phosphorus / Month"
        # carries about 150 characters, so any cutoff generous enough to spare
        # Georgian Bay disarms the check on the fabrication it exists to catch.
        #
        # So the page calibrates itself. If ANY label the model claimed is found
        # in the OCR, the text layer demonstrably works, and a label that is
        # missing from it is suspicious. If NOT ONE label can be found, the text
        # layer is not evidence either way and its silence is not a refusal.
        # On the plot page "Phosphorus" is found and "Month" is not, so the
        # fabrication is caught; on Georgian Bay nothing is found, so nothing is
        # thrown away.
        if _page_can_referee(candidates, page.text):
            unverified = [
                label for label in (row, col)
                if label and not _label_on_page(label, page.text)
            ]
            if unverified:
                rejected.append({
                    "why": f"label(s) not found in the page's OCR text: "
                           f"{', '.join(repr(u) for u in unverified)} -- the model "
                           "may have invented the table structure",
                    "candidate": c,
                })
                continue
            label_check = "verified against the page's OCR"
        else:
            label_check = (
                f"not checked: only {len(page.text.strip())} characters of OCR "
                "survived on this page, too little to confirm or refute a heading"
            )

        value = _to_float(c.get("value"))
        if value is None:
            rejected.append({"why": "no numeric value", "candidate": c})
            continue

        model_conf = _to_float(c.get("confidence"))
        model_conf = 0.5 if model_conf is None else max(0.0, min(1.0, model_conf))
        # Vision reading of a degraded table is harder than reading a clean
        # sentence, and the OCR-confidence signal does not apply here at all,
        # so the ceiling is deliberately lower than the prose path's.
        confidence = round(0.8 * model_conf, 4)

        where = " / ".join(x for x in (row, col) if x)
        stream = str(c.get("stream") or "unknown").strip().lower()
        rec = Record(
            kind=kind,  # type: ignore[arg-type]
            parameter=parameter,
            value=value,
            unit=(str(c["unit"]).strip() if c.get("unit") else None),
            qualifier=(str(c["qualifier"]).strip().lower() if c.get("qualifier") else None),  # type: ignore[arg-type]
            stream=stream if stream in
            ("influent", "effluent", "ambient", "raw", "treated", "unknown") else "unknown",  # type: ignore[arg-type]
            period=(str(c["period"]).strip() if c.get("period") else None),
            confidence=confidence,
            provenance=Provenance(
                identifier=page.identifier,
                page=page.page,
                source_text=f"table cell [{where}]",
                extractor=client.name,
                path="vision",
            ),
            raw={"row_label": row, "column_label": col, "model_confidence": model_conf,
                 # Whether this page's own OCR was able to confirm the headings,
                 # so weaker evidence travels with the record instead of being
                 # forgotten the moment it leaves this function.
                 "label_check": label_check},
        )
        problems = rec.problems()
        if problems:
            rejected.append({"why": "; ".join(problems), "candidate": c})
            continue
        records.append(rec)

    _disambiguate_columns(records)
    return VisionResult(records=records, rejected=rejected, raw_response=raw)


def _disambiguate_columns(records: list[Record]) -> None:
    """Fold a column heading into the parameter when the row alone is ambiguous.

    A table is two-dimensional and a parameter name is not. An expenditure table
    gives, for 1981-82, In-House 15, Contracts 100 and Total 115 -- three
    different measurements whose only distinguishing feature is the column. Left
    alone they share an identity, and the dispute ledger reports a department's
    budget as a three-way contradiction.

    This is the table form of a mistake already made twice: Owen Sound's sewage
    plant and water works merged under one place, and Brantford's influent and
    effluent BOD merged under one parameter. Both times the fix was to admit
    that the identity was missing a field.

    Only applied where it is needed. If every record under a parameter comes
    from the same column, the column adds nothing and the name is left alone.
    """
    by_parameter: dict[str, list[Record]] = {}
    for record in records:
        column = str((record.raw or {}).get("column_label") or "").strip()
        if column:
            by_parameter.setdefault(record.parameter.strip().lower(), []).append(record)

    for group in by_parameter.values():
        columns = {str((r.raw or {}).get("column_label") or "").strip() for r in group}
        if len(columns) < 2:
            continue
        for record in group:
            column = str((record.raw or {}).get("column_label") or "").strip()
            if column and _norm(column) not in _norm(record.parameter):
                record.parameter = f"{record.parameter} ({column})"
