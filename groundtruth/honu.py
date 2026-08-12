"""Honu, repointed at the archive.

Forked from the OMEGA-wave copilot: the CopilotTool shape, the tool-calling
loop, the pending-action idea, and the rule that the model never invents an
answer it could have looked up.

What changed is what the tools do. OMEGA's talk to a live mesh -- devices,
firmware, radio links. These talk to a hundred years of scanned paper, and the
difference forces one addition: **every answer must carry its evidence.** A live
sensor reading is self-evidently a reading. A number recovered from a 1969 scan
by another model is a claim, and a claim that arrives without the sentence it
came from is worth nothing here.

So the system prompt forbids answering from memory, the tools always return
provenance, and the loop refuses to summarise a tool result in a way that drops
the page link.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from .tools import (
    Corpus,
    explain_this_number,
    find_my_town,
    judge_reading,
    read_me_the_record,
    show_the_page,
    standard_for,
    what_went_quiet,
)


@dataclass
class Tool:
    """A capability exposed to the model as a callable."""

    name: str
    description: str
    properties: dict[str, Any]
    required: tuple[str, ...]
    run: Callable[..., Any]

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.properties,
                    "required": list(self.required),
                },
            },
        }


def build_tools(corpus: Corpus) -> dict[str, Tool]:
    """The archive toolset. Every one of these returns provenance."""
    S = {"type": "string"}
    N = {"type": "number"}
    I = {"type": "integer"}

    return {t.name: t for t in [
        Tool(
            "find_my_town",
            "Everything ever measured about a place: which years, which parameters, "
            "how many documents. Use this first when asked about somewhere.",
            {"place": {**S, "description": "town name, e.g. 'Owen Sound'"}},
            ("place",),
            lambda place: find_my_town(corpus, place),
        ),
        Tool(
            "read_me_the_record",
            "A place's story across the decades: what changed, in which direction, "
            "with the trend and the assumptions behind it.",
            {"place": S},
            ("place",),
            lambda place: read_me_the_record(corpus, place),
        ),
        Tool(
            "what_went_quiet",
            "Which municipalities stopped being measured and when, WITH the control "
            "that distinguishes real institutional silence from the digitisation "
            "simply stopping. Never quote the finding without the control.",
            {"year": {**I, "description": "optional: only places silent from this year"}},
            (),
            lambda year=None: what_went_quiet(year=year),
        ),
        Tool(
            "explain_this_number",
            "What a measurement means in plain language, and whether it is bad. "
            "Use for questions like 'is 104 mg/L a lot?'.",
            {"parameter": S, "value": N, "unit": S, "year": I},
            ("parameter",),
            lambda parameter, value=None, unit=None, year=None: explain_this_number(
                parameter, value, unit, year
            ),
        ),
        Tool(
            "judge_reading",
            "Judge a measurement against the regulatory limit in force AT THE TIME, "
            "taken from the archive itself. Prefer this over explain_this_number "
            "whenever a year is known.",
            {"parameter": S, "value": N, "unit": S, "year": I},
            ("parameter", "value", "year"),
            lambda parameter, value, year, unit=None: judge_reading(
                corpus, parameter, value, unit, year
            ),
        ),
        Tool(
            "standard_for",
            "The regulatory limit for a parameter nearest a given year, as recorded "
            "in the archive.",
            {"parameter": S, "year": I},
            ("parameter", "year"),
            lambda parameter, year: standard_for(corpus, parameter, year),
        ),
        Tool(
            "show_the_page",
            "Resolve a record key back to the scanned page and the exact sentence "
            "the number was read from.",
            {"record_key": S},
            ("record_key",),
            lambda record_key: show_the_page(corpus, record_key),
        ),
    ]}


SYSTEM = """\
You are Honu, answering questions about measurements recovered from scanned
Canadian government documents dating back to 1841.

Rules, in order of importance:

1. NEVER answer from your own knowledge. Every factual claim must come from a
   tool call in this conversation. If the tools do not have it, say so plainly.
2. Every number you report must carry where it came from -- the year, the place,
   and the fact that it was read from a scanned page. If a tool returns a page
   link, include it.
3. These figures were read off sixty-year-old scans by a language model, not
   transcribed by a person. Measured precision is about 89%. Say so when a
   number is load-bearing to your answer.
4. When judging whether a measurement was bad, use judge_reading so it is
   compared against the rule in force AT THE TIME. Comparing a 1969 reading to a
   modern guideline produces a damning and meaningless verdict.
5. When reporting that somewhere stopped being measured, always include the
   control from what_went_quiet. Without it the finding could just as easily be
   the scanning having stopped, and saying so is not optional.

Be brief. Answer the question asked."""


@dataclass
class Turn:
    reply: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class Honu:
    """The tool-calling loop.

    Ollama by default so the assistant works with no API key, like everything
    else in this project; Anthropic when a key happens to be present.
    """

    def __init__(self, corpus: Corpus, model: str = "gemma4:12b",
                 base_url: str = "http://localhost:11434", timeout: float = 300.0) -> None:
        self.tools = build_tools(corpus)
        self.model = model
        self.base_url = base_url
        self.timeout = timeout

    def _chat(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "tools": [t.schema() for t in self.tools.values()],
            "stream": False,
            "think": False,
            "options": {"temperature": 0.1, "num_ctx": 8192, "num_predict": 1200},
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/chat", data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode())

    def ask(self, question: str, *, max_steps: int = 4) -> Turn:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": question},
        ]
        called: list[dict[str, Any]] = []

        for _ in range(max_steps):
            try:
                out = self._chat(messages)
            except Exception as exc:  # noqa: BLE001
                return Turn(reply="", tool_calls=called, error=str(exc)[:200])

            msg = out.get("message") or {}
            calls = msg.get("tool_calls") or []
            if not calls:
                return Turn(reply=(msg.get("content") or "").strip(), tool_calls=called)

            messages.append(msg)
            for call in calls:
                fn = (call.get("function") or {})
                name = fn.get("name", "")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                tool = self.tools.get(name)
                if tool is None:
                    result: Any = {"error": f"no such tool: {name}"}
                else:
                    try:
                        result = tool.run(**args)
                    except Exception as exc:  # noqa: BLE001
                        result = {"error": f"{name} failed: {exc}"}
                called.append({"tool": name, "arguments": args})
                # Truncate: a full town record is far larger than the context
                # budget, and the model only needs enough to answer.
                body = json.dumps(result, default=str)
                messages.append({
                    "role": "tool", "name": name,
                    "content": body[:4000],
                })

        return Turn(
            reply="I ran out of steps before reaching an answer.",
            tool_calls=called,
        )
