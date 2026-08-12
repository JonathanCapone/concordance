"""Path A: reading measurements out of prose.

The central finding this project rests on is that OCR preserved prose and
destroyed tables. The numbers in a 1969 municipal report are not in a grid; they
are in sentences:

    "The average influent BOD and suspended solids were 104 mg/1 and 224 mg/1
     respectively."

So extraction is a reading task, which language models do reliably, rather than
a table-recognition task off a degraded scan, which they do not.

Two guards make the output trustworthy:

1. **Verbatim provenance.** The model must return the exact sentence it read a
   value from. We then check that sentence actually occurs on the page. A model
   that invents a number will almost always invent the sentence too, so this
   catches fabrication for the cost of a substring search.
2. **Compound confidence.** Reading confidence is the model's own certainty
   multiplied by how legible the scan was. A confident reading of an illegible
   page is not a confident measurement.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from .models import PageText, Provenance, Record

DEFAULT_OLLAMA_MODEL = "gemma4:12b"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"


# --------------------------------------------------------------------------
# model backends
# --------------------------------------------------------------------------

class ModelClient(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str: ...


@dataclass
class OllamaClient:
    """Local models. The default, so the pipeline needs no API key to run."""

    model: str = DEFAULT_OLLAMA_MODEL
    base_url: str = "http://localhost:11434"
    timeout: float = 1800.0

    @property
    def name(self) -> str:
        return f"ollama:{self.model}"

    #: Disable the model's hidden reasoning pass.
    #:
    #: Measured on gemma4:12b: producing the string `[{"a":1}]` cost 121 tokens
    #: and 32.7s with thinking on, and 7 tokens and 2.4s with it off -- a 17x
    #: difference for identical output. Ollama strips the reasoning from the
    #: `response` field, so on a full page the model would reason past the token
    #: budget and return an empty string, which looks like "the extractor found
    #: nothing" rather than "the extractor never answered".
    #:
    #: Extraction here is transcription, not deduction: the answer is in the
    #: sentence being read. There is nothing to reason about.
    think: bool = False

    def complete(self, system: str, user: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "system": system,
                "prompt": user,
                "stream": False,
                "think": self.think,
                # Deterministic: the same page must extract the same way across
                # runs, or the accuracy harness measures noise.
                #
                # num_predict is a wall-clock budget, not a quality knob.
                # Measured throughput for gemma4:12b on this machine is ~7.9
                # tokens/sec, so 8192 tokens is ~17 minutes for ONE page -- a
                # model that rambles instead of stopping will burn the entire
                # budget. A dense page yields ~20 records at ~70 tokens each,
                # so 3000 covers real output with headroom, and the salvage
                # parser recovers whatever completed if it does truncate.
                "options": {
                    "temperature": 0.0,
                    "num_ctx": 8192,
                    "num_predict": 3000,
                    # Halt as soon as the array closes rather than letting the
                    # model continue into commentary it was told not to write.
                    "stop": ["\n]", "]\n\n", "```\n\n"],
                },
            }
        ).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode()).get("response", "")


@dataclass
class AnthropicClient:
    """Optional, higher accuracy. Never required -- the user supplies their own key."""

    model: str = DEFAULT_ANTHROPIC_MODEL
    api_key: str | None = None
    max_tokens: int = 4096
    timeout: float = 180.0

    @property
    def name(self) -> str:
        return f"anthropic:{self.model}"

    def complete(self, system: str, user: str) -> str:
        key = self.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("no ANTHROPIC_API_KEY; use OllamaClient instead")
        payload = json.dumps(
            {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "temperature": 0,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            }
        ).encode()
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


def default_client() -> ModelClient:
    """Anthropic if a key happens to be present, else local. Never fails for lack of a key."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicClient()
    return OllamaClient()


# --------------------------------------------------------------------------
# the prompt
# --------------------------------------------------------------------------

SYSTEM = """\
You read scanned Canadian government reports and recover the measurements in them.

They come from every part of government: water and sewage, but also education,
agriculture, forestry, mining, energy, health, housing, transport, justice,
trade and the census. A measurement is any quantity the page states about the
world. Do not restrict yourself to scientific or environmental quantities.

Very often the unit IS the thing being counted, and there is no unit symbol at
all. These are all measurements:

    "75 elementary schools under the aegis of the Hamilton Board of Education"
        -> parameter "elementary schools", value 75, unit "schools"
    "more than 50 percent of all steel produced in the country"
        -> parameter "share of national steel production", value 50, unit "%"
    "leasing of which runs to about 7 percent of the board's annual budget"
        -> parameter "bus leasing share of budget", value 7, unit "%"
    "the average rent now paid, namely $357.00 per month"
        -> parameter "monthly rent", value 357, unit "$/month"
    "a yield of 32 bushels to the acre"
        -> parameter "wheat yield", value 32, unit "bushels/acre"
    "the population of the town was 55,201 at the 1961 census"
        -> parameter "population", value 55201, unit "persons"

The text comes from OCR of a document that may be sixty years old. It will
contain scanning errors. "mg/1" almost always means "mg/L". Numbers may have
stray spaces, e.g. "8. 8 million gallons" means 8.8. Letters often stand where
digits were: "I5" is 15, "3I per cent" is 31 per cent, "SOfo" is 50%.

A sentence that names a year other than the report's year may be comparing two
years. Put each value under the year the sentence gives it, not automatically
under the report's year:

    (in a 1969 report) "The average solids concentration of 5.1% was less than
    the 1968 average of 5.3%"
        -> 5.1 belongs to 1969, and 5.3 belongs to 1968

Return ONLY a JSON array. No prose, no markdown fence. Each element:

{
  "kind":       "observation" | "standard" | "design" | "conclusion",
  "parameter":  what was measured, e.g. "BOD", "suspended solids", "chlorine dosage",
  "value":      the number, or null,
  "unit":       e.g. "mg/L", "%", "million gallons", "cu ft",
  "qualifier":  "average"|"mean"|"median"|"maximum"|"minimum"|"total"|"percent"|"count"|"point"|null,
  "stream":     "influent"|"effluent"|"ambient"|"raw"|"treated"|"unknown",
  "place":      the place it refers to, or null,
  "period":     the time it refers to, e.g. "1969", "1969-11", or null,
  "confidence": 0.0 to 1.0 -- how sure you are you read this correctly,
  "source_text": the EXACT sentence or line from the text that this came from
}

Distinguishing the four kinds is the most important thing you do:

- "observation" is what was actually MEASURED.
    "The average influent BOD ... were 104 mg/1"  -> observation
- "standard" is a REGULATORY LIMIT or objective, not a measurement.
    "The Maximum Acceptable Concentration of nitrate is 10 mg/L"  -> standard
- "design" is what equipment was BUILT to handle -- a specification.
    A "DESIGN DATA" section reading "BOD - Raw Sewage 180 mg/1"  -> design
- "conclusion" is the author's judgement, often with no number.
    "The plant operated above capacity 85% of the time"  -> conclusion

A percentage is NOT automatically a removal efficiency. Read what it counts:
    "an average removal of 64% BOD"                  -> observation, BOD removal
    "the objective was exceeded 20 per cent of the time"
        -> observation, parameter "BOD exceedance frequency" -- this counts HOW
           OFTEN a limit was breached, not how much was taken out. Filing it as
           removal inverts its meaning: 20% exceedance is good, 20% removal is bad.
    "80% of the time the plant operated above design capacity"
        -> observation, parameter "capacity exceedance frequency"
Use the word "frequency" in the parameter whenever the number counts occasions
rather than quantity.

A design value and an observation can be the same parameter, same unit, same
plant, in the same document. Confusing them corrupts the record. When a value
appears under a heading like DESIGN DATA, DESIGN FLOW, or in an equipment
specification list, it is "design".

Rules:
- source_text MUST be copied exactly from the input. Do not paraphrase it.
- If you cannot find a real sentence for a value, do not emit that value.
- Emit one element per measured value. "104 mg/1 and 224 mg/1 respectively"
  is TWO observations, not one.
- Do not invent. An empty array is a correct answer for a page with no measurements.
- OMIT any field that would be null. Only "kind", "parameter" and "source_text"
  are always required. Shorter output is better.
- When several values share one sentence, repeat that same sentence as the
  source_text for each. Do not shorten it.
- Output the array and nothing else. Stop immediately after the closing bracket.
"""

USER_TEMPLATE = """\
Document: {title}
Publisher: {publisher}
Year: {year}
Page: {page}

--- BEGIN PAGE TEXT ---
{text}
--- END PAGE TEXT ---

Return the JSON array."""


# --------------------------------------------------------------------------
# extraction
# --------------------------------------------------------------------------

def _normalize(s: str) -> str:
    """Collapse whitespace and drop punctuation, for tolerant substring matching.

    OCR spacing is chaotic ("8. 8 million"), and the model will silently tidy it
    when quoting. Comparing normalized forms keeps the provenance check strict
    about *content* while forgiving about *spacing*.
    """
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _salvage_objects(raw: str) -> list[dict[str, Any]]:
    """Recover every complete {...} object from a truncated or dirty response.

    Generation gets cut off mid-array often enough that discarding the whole
    page when the closing bracket is missing would throw away a dozen good
    records to save one incomplete one. Scans a bracket depth counter, respecting
    strings and escapes, and parses each balanced object independently.
    """
    out: list[dict[str, Any]] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False

    for i, ch in enumerate(raw):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    try:
                        obj = json.loads(raw[start:i + 1])
                        if isinstance(obj, dict):
                            out.append(obj)
                    except json.JSONDecodeError:
                        pass
                    start = -1
    return out


def _parse_json_array(raw: str) -> list[dict[str, Any]]:
    """Pull records out of a model response, however mangled.

    Local models wrap output in prose or code fences despite instructions, and
    long pages get truncated mid-array. Try clean parse, then whole-array, then
    salvage individual objects.
    """
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw).strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        pass
    start, end = raw.find("["), raw.rfind("]")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(raw[start:end + 1])
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
    return _salvage_objects(raw)


def _to_float(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[,\s$]", "", str(v))
    m = re.search(r"-?\d*\.?\d+", s)
    return float(m.group(0)) if m else None


@dataclass
class ExtractionResult:
    records: list[Record]
    rejected: list[dict[str, Any]]     # what was dropped, and why
    raw_response: str

    @property
    def kept(self) -> int:
        return len(self.records)


def extract_prose(
    page: PageText,
    *,
    client: ModelClient | None = None,
    title: str = "",
    publisher: str = "",
    year: str = "",
) -> ExtractionResult:
    """Read one page. Returns records plus an audit trail of what was rejected."""
    client = client or default_client()
    user = USER_TEMPLATE.format(
        title=title or "(unknown)",
        publisher=publisher or "(unknown)",
        year=year or "(unknown)",
        page=page.page,
        text=page.text[:12000],
    )
    raw = client.complete(SYSTEM, user)
    candidates = _parse_json_array(raw)

    page_norm = _normalize(page.text)
    records: list[Record] = []
    rejected: list[dict[str, Any]] = []

    for c in candidates:
        if not isinstance(c, dict):
            continue
        source = str(c.get("source_text") or "").strip()
        kind = str(c.get("kind") or "").strip().lower()
        parameter = str(c.get("parameter") or "").strip()

        if kind not in ("observation", "standard", "design", "conclusion"):
            rejected.append({"why": f"unknown kind {kind!r}", "candidate": c})
            continue
        if not parameter:
            rejected.append({"why": "empty parameter", "candidate": c})
            continue

        # The hallucination guard. A fabricated value nearly always comes with a
        # fabricated sentence, and a sentence that isn't on the page is not
        # evidence of anything.
        if not source:
            rejected.append({"why": "no source_text", "candidate": c})
            continue
        if _normalize(source) not in page_norm:
            rejected.append({"why": "source_text not found on page", "candidate": c})
            continue

        model_conf = _to_float(c.get("confidence"))
        model_conf = 0.5 if model_conf is None else max(0.0, min(1.0, model_conf))
        # Legibility of the scan bounds how much a confident reading is worth.
        scan_conf = page.ocr_confidence if page.ocr_confidence is not None else 1.0
        confidence = round(model_conf * (0.5 + 0.5 * scan_conf), 4)

        qualifier = c.get("qualifier")
        stream = str(c.get("stream") or "unknown").strip().lower()
        record = Record(
            kind=kind,  # type: ignore[arg-type]
            parameter=parameter,
            value=_to_float(c.get("value")),
            unit=(str(c["unit"]).strip() if c.get("unit") else None),
            qualifier=(str(qualifier).strip().lower() if qualifier else None),  # type: ignore[arg-type]
            stream=stream if stream in
            ("influent", "effluent", "ambient", "raw", "treated", "unknown") else "unknown",  # type: ignore[arg-type]
            place=(str(c["place"]).strip() if c.get("place") else None),
            period=(str(c["period"]).strip() if c.get("period") else None),
            confidence=confidence,
            provenance=Provenance(
                identifier=page.identifier,
                page=page.page,
                source_text=source,
                extractor=client.name,
                path="prose",
            ),
            raw={"model_confidence": model_conf, "ocr_confidence": scan_conf},
        )

        problems = record.problems()
        if problems:
            rejected.append({"why": "; ".join(problems), "candidate": c})
            continue
        records.append(record)

    return ExtractionResult(records=records, rejected=rejected, raw_response=raw)
