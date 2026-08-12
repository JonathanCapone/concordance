"""Ask for data. If nobody has read it yet, you read it -- for everyone.

This is the front door, and the whole point of it is that contributing is not a
separate act. There is no volunteer mode, no queue to join, no altruism
required. You ask for the record of a place or a subject:

  * if the library already has it, you get it immediately
  * if you are the first person to want it, your machine reads it, and it is in
    the library from then on

The cost falls on whoever cares first, which is also the person most willing to
wait. Everyone after them pays nothing. The archive therefore gets read in order
of what people actually want to know, which is a far better ordering than any
plan we could impose, and it needs no coordination beyond "has this been read".

What the person asking never has to do: pick documents, review vocabulary,
judge a reading, package a submission, or know that any of this happened. They
asked for Owen Sound and they got Owen Sound. Sometimes in a second, sometimes
in an hour.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .archive import Archive
from .contribute import make_bundle, verify_bundle
from .parameters import facility_of, resolve as resolve_parameter
from .router import Path as RPath, route

LIBRARY = Path("data/results")


@dataclass
class Answer:
    """What came back, and where it came from."""

    query: str
    records: list[dict[str, Any]] = field(default_factory=list)
    source: str = "library"          # "library" | "read now" | "empty"
    documents: int = 0
    seconds: float = 0.0
    verified: int = 0
    contributed: bool = False
    unknown_parameters: list[str] = field(default_factory=list)
    note: str = ""

    def describe(self) -> str:
        if self.source == "library":
            return (f"{len(self.records)} readings for {self.query!r}, already in the "
                    f"library from {self.documents} documents.")
        if self.source == "read now":
            return (f"{len(self.records)} readings for {self.query!r}, read from "
                    f"{self.documents} documents in {self.seconds/60:.0f} minutes. "
                    "Nobody had read these before; they are in the library now.")
        return f"Nothing found for {self.query!r}. {self.note}"


def _load_library() -> list[dict[str, Any]]:
    skip = {"gold_report", "metadata_proposals", "silence_report", "corpus_census",
            "audit", "cost_model", "vocab_proposals"}
    out: list[dict[str, Any]] = []
    for path in LIBRARY.glob("*.json"):
        if path.stem in skip:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        out.extend(payload.get("records") or [])
    return out


def _held(query: str, records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    want = query.strip().lower()
    return [r for r in records if want in str(r.get("place") or "").lower()]


def ask(
    query: str,
    *,
    read_if_missing: bool = True,
    extractor: Callable[..., Any] | None = None,
    model: str = "gemma4:12b",
    max_documents: int = 20,
    on_progress: Callable[[str], None] | None = None,
) -> Answer:
    """Get the record for a place. Read it first if nobody has.

    `read_if_missing=False` turns this into a pure lookup, for anyone who wants
    an answer now or not at all.
    """
    say = on_progress or (lambda _msg: None)
    t0 = time.time()

    held = _held(query, _load_library())
    if held:
        docs = {(r.get("provenance") or {}).get("identifier") for r in held}
        return Answer(query=query, records=held, source="library",
                      documents=len(docs), seconds=time.time() - t0)

    if not read_if_missing:
        return Answer(query=query, source="empty",
                      note="Not in the library yet, and reading was not requested.")

    archive = Archive()
    items = [
        it for it in archive.iter_items(title_contains=query.lower())
        if "annual report" in str(it.get("title", "")).lower()
        or "sewage treatment plant" in str(it.get("title", "")).lower()
    ][:max_documents]

    if not items:
        return Answer(query=query, source="empty",
                      note="No documents in the collection match that.")

    say(f"Nobody has read {query} yet. {len(items)} documents to work through.")

    from .extract import OllamaClient, extract_prose
    client = OllamaClient(model=model)
    extractor = extractor or extract_prose

    records: list[dict[str, Any]] = []
    unknown: set[str] = set()

    for n, item in enumerate(items, 1):
        ident = item["identifier"]
        title = str(item.get("title") or "")
        year = str(item.get("year") or "")
        facility = facility_of(title)
        try:
            pages = archive.pages(ident)
        except Exception:  # noqa: BLE001
            continue
        worth = [p for p in pages if RPath.PROSE in route(p).paths]
        say(f"  [{n}/{len(items)}] {year}: {len(worth)} pages worth reading")

        for page in worth:
            try:
                result = extractor(page, client=client, title=title, year=year)
            except Exception:  # noqa: BLE001
                continue
            for rec in result.records:
                d = rec.to_dict()
                d.setdefault("place", query)
                d["facility"] = facility
                if not d.get("period") and year:
                    d["period"] = year
                records.append(d)
                # Vocabulary gaps are collected and reported home. The person
                # asking is never shown them and never has to do anything about
                # them -- maintaining the vocabulary is our job, not theirs.
                if resolve_parameter(d.get("parameter") or "", d.get("unit")) is None:
                    unknown.add(str(d.get("parameter") or "").strip())

    # Verify our own work before adding it to the shared library, on exactly the
    # same terms a stranger's contribution would be checked. Reading it yourself
    # is not a reason to trust it.
    bundle = make_bundle(records, contributor="local", note=query)
    verdict = verify_bundle(bundle, archive=archive)

    contributed = False
    if verdict.accepted:
        LIBRARY.mkdir(parents=True, exist_ok=True)
        slug = query.lower().replace(" ", "-")
        (LIBRARY / f"{slug}.json").write_text(json.dumps({
            "place": query, "model": client.name, "n_records": len(records),
            "verified": verdict.verified, "records": records,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        contributed = True
        say(f"Verified {verdict.verified}/{verdict.total} readings against the scans "
            "and added them to the library.")
    elif records:
        say(f"Verification failed on {len(verdict.failed)} readings; NOT added to the "
            "library. The readings are returned to you but not shared.")

    return Answer(
        query=query, records=records, source="read now",
        documents=len(items), seconds=time.time() - t0,
        verified=verdict.verified, contributed=contributed,
        unknown_parameters=sorted(unknown),
    )
