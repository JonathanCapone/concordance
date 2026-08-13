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

import hashlib
import json
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from . import vocabulary
from .contribute import _value_in_quote
from .models import PageText, Provenance, Record

DEFAULT_OLLAMA_MODEL = "gemma4:12b"
PARAMETER_NAMING_VERSION = "controlled-vocabulary-v1"
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
    "Total mileage was 334.15 miles"
        -> parameter "mileage", value 334.15, unit "miles"
    "The incubation period lasted from 20 to 30 days"
        -> parameter "incubation period", values 20 and 30, unit "days"
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

One document routinely covers many facilities, and the same parameter then means
different things a paragraph apart. A page describing a city's hospitals gives
430 beds, 640 beds, 620 beds and 420 beds -- four hospitals, not a contradiction
-- and each sentence names which. Always fill "facility" when the sentence names
what is being measured; without it those four readings collapse into one and are
reported as a disagreement.

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
  "parameter_status": "controlled" if parameter is copied from the supplied
                vocabulary, otherwise "proposed",
  "value":      the number, or null,
  "unit":       e.g. "mg/L", "%", "million gallons", "cu ft",
  "qualifier":  "average"|"mean"|"median"|"maximum"|"minimum"|"total"|"percent"|"count"|"point"|null,
  "stream":     "influent"|"effluent"|"ambient"|"raw"|"treated"|"unknown",
  "place":      the place it refers to, or null,
  "facility":   the specific thing measured, when the sentence names one, e.g.
                "Hamilton General Hospital", "Hamilton Board of Education",
                "water pollution control plant", or null,
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
- OMIT any field that would be null. Only "kind", "parameter",
  "parameter_status" and "source_text" are always required. Shorter output is
  better.
- When several values share one sentence, repeat that same sentence as the
  source_text for each. Do not shorten it.
- Output the array and nothing else. Stop immediately after the closing bracket.
"""

VOCABULARY_TEMPLATE = """\
CONTROLLED MEASUREMENT VOCABULARY

The list below contains reusable measurement types found in this archive. For
each output element, choose the one term that means what the sentence measured,
copy its spelling exactly into "parameter", and set "parameter_status" to
"controlled".

Keep sentence context out of the parameter name. Place, facility, period and
qualifier belong in their own fields; do not weld a report-specific
organisation or comparison onto the name. A parameter must be able to recur in
another report: use "mileage", not "mileage of railway operated by this
commission".

The list is shortened for this document and may not contain the right term. Do
not force a near match. When no listed term fits, put a short, reusable proposed
term in "parameter" and set "parameter_status" to "proposed". That explicit
proposal is how a genuinely missing term is found and reviewed.

--- BEGIN CONTROLLED VOCABULARY ---
{terms}
--- END CONTROLLED VOCABULARY ---
"""

NO_VOCABULARY = """\
CONTROLLED MEASUREMENT VOCABULARY

No controlled vocabulary is available in this clone yet. Extraction must still
continue. Use a short, reusable measurement type in "parameter", never a
sentence-specific description, and set "parameter_status" to "proposed" so it
can be reviewed and added later.
"""


def _system_prompt(
    vocab: vocabulary.Vocabulary,
    *,
    hint: str = "",
    rendered_terms: str | None = None,
) -> str:
    """Add the relevant archive vocabulary without making it a prerequisite."""
    terms = vocab.for_prompt(hint=hint) if rendered_terms is None else rendered_terms
    instructions = VOCABULARY_TEMPLATE.format(terms=terms) if terms else NO_VOCABULARY
    return f"{SYSTEM.rstrip()}\n\n{instructions}"


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


#: A month standing alone is a time, not a town. Reading a monthly table, the
#: model put the row label in `place`: 31 Brantford records landed under
#: "January", "February", "March" and so on, and the frontier duly proposed
#: reading "April's council minutes".
#:
#: Only bare month names are moved. "March Township" and "Bay of May" stay put,
#: because the failure being corrected is a row label misfiled, not a place that
#: happens to share a word with the calendar.
_MONTHS = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "jun": "06",
    "jul": "07", "aug": "08", "sep": "09", "sept": "09", "oct": "10",
    "nov": "11", "dec": "12",
}


def _month_of(text: str | None) -> str | None:
    return _MONTHS.get(str(text or "").strip().strip(".").lower())


def _place_of(c: dict[str, Any]) -> str | None:
    """The place, unless the model handed us a month.

    Returning None lets the caller's own default apply -- the town it asked to
    read -- which is a better answer than a calendar month and better than
    guessing here.
    """
    place = str(c.get("place") or "").strip()
    if not place or _month_of(place):
        return None
    return place


def _period_of(c: dict[str, Any]) -> str | None:
    """The period, with a misfiled month folded back into it.

    A monthly row of a 1962 table is 1962-03, and that is more precise than the
    year alone -- so the misread is worth recovering rather than discarding.
    """
    period = str(c.get("period") or "").strip()
    month = _month_of(c.get("place"))
    if not month:
        return period or None
    if period[:4].isdigit() and len(period) == 4:
        return f"{period[:4]}-{month}"
    return period or None


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
    vocab = vocabulary.load()
    # Select from exactly the evidence the model will see. Complete phrase
    # matches on the page are a much stronger and safer retrieval signal than
    # generic report titles, and this text is used only for ranking -- it is not
    # duplicated in the prompt.
    page_text = page.text[:12000]
    vocab_hint = "\n".join(part for part in (title, publisher, page_text) if part)
    rendered_vocabulary = vocab.for_prompt(hint=vocab_hint)
    system = _system_prompt(vocab, hint=vocab_hint, rendered_terms=rendered_vocabulary)
    prompted_term_count = sum(
        1 for line in rendered_vocabulary.splitlines()
        if line.strip() and not line.startswith("#")
    )
    vocabulary_prompt_digest = hashlib.sha256(
        rendered_vocabulary.encode("utf-8")
    ).hexdigest()[:20]
    user = USER_TEMPLATE.format(
        title=title or "(unknown)",
        publisher=publisher or "(unknown)",
        year=year or "(unknown)",
        page=page.page,
        text=page_text,
    )
    raw = client.complete(system, user)
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
        model_parameter = parameter

        if kind not in ("observation", "standard", "design", "conclusion"):
            rejected.append({"why": f"unknown kind {kind!r}", "candidate": c})
            continue
        if not parameter:
            rejected.append({"why": "empty parameter", "candidate": c})
            continue

        # Do not trust the model to declare its own proposal controlled. The
        # file is authoritative: aliases collapse to the canonical spelling,
        # while anything it cannot match remains a visible proposal.
        controlled_term = vocab.match(parameter)
        parameter_status = "controlled" if controlled_term else "proposed"
        if controlled_term:
            parameter = controlled_term.canonical

        # The hallucination guard. A fabricated value nearly always comes with a
        # fabricated sentence, and a sentence that isn't on the page is not
        # evidence of anything.
        if not source:
            rejected.append({"why": "no source_text", "candidate": c})
            continue
        if _normalize(source) not in page_norm:
            rejected.append({"why": "source_text not found on page", "candidate": c})
            continue

        value = _to_float(c.get("value"))
        value_state, value_evidence = _value_in_quote(value, source)
        if value_state == "failed":
            rejected.append({"why": value_evidence, "candidate": c})
            continue

        model_conf = _to_float(c.get("confidence"))
        model_conf = 0.5 if model_conf is None else max(0.0, min(1.0, model_conf))
        # Legibility of the scan bounds how much a confident reading is worth.
        scan_conf = page.ocr_confidence if page.ocr_confidence is not None else 1.0
        confidence = round(model_conf * (0.5 + 0.5 * scan_conf), 4)

        qualifier = c.get("qualifier")
        stream = str(c.get("stream") or "unknown").strip().lower()
        model_parameter_status = str(c.get("parameter_status") or "").strip().lower()
        raw_metadata: dict[str, Any] = {
            "model_confidence": model_conf,
            "ocr_confidence": scan_conf,
            "model_parameter": model_parameter,
            "parameter_status": parameter_status,
            "value_evidence": value_evidence or "exactly present in source_text",
            # Old extraction records have neither of these fields.  Keeping the
            # prompt generation and vocabulary size on each new record makes a
            # batch that crosses this rollout auditable instead of making old
            # free-named and new vocabulary-guided output look homogeneous.
            "parameter_naming_version": PARAMETER_NAMING_VERSION,
            "vocabulary_terms_available": len(vocab),
            "vocabulary_terms_prompted": prompted_term_count,
            "vocabulary_prompt_digest": vocabulary_prompt_digest,
        }
        if model_parameter_status in ("controlled", "proposed"):
            raw_metadata["model_parameter_status"] = model_parameter_status

        record = Record(
            kind=kind,  # type: ignore[arg-type]
            parameter=parameter,
            value=value,
            unit=(str(c["unit"]).strip() if c.get("unit") else None),
            qualifier=(str(qualifier).strip().lower() if qualifier else None),  # type: ignore[arg-type]
            stream=stream if stream in
            ("influent", "effluent", "ambient", "raw", "treated", "unknown") else "unknown",  # type: ignore[arg-type]
            place=_place_of(c),
            # Taken from the sentence when the model names one. The caller
            # overwrites this with the document's facility only when it is
            # empty, because a page describing four hospitals knows which is
            # which and the title does not.
            facility=(str(c["facility"]).strip() if c.get("facility") else None),
            period=_period_of(c),
            confidence=confidence,
            provenance=Provenance(
                identifier=page.identifier,
                page=page.page,
                source_text=source,
                extractor=client.name,
                path="prose",
            ),
            raw=raw_metadata,
        )

        problems = record.problems()
        if problems:
            rejected.append({"why": "; ".join(problems), "candidate": c})
            continue
        records.append(record)

    return ExtractionResult(records=records, rejected=rejected, raw_response=raw)
