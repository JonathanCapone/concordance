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
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .archive import Archive
from .contribute import make_bundle, verify_bundle
from .parameters import facility_of, resolve as resolve_parameter
from .places import scope_record_dict
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
    #: How many records the archive stood behind and the library now holds.
    #: Distinct from len(records): a read can recover 40 readings, publish 37,
    #: and have 3 fail their own evidence check -- and the caller must be able
    #: to say that rather than "read 40" over a library holding 37.
    published: int = 0
    contributed: bool = False
    unknown_parameters: list[str] = field(default_factory=list)
    note: str = ""

    def describe(self) -> str:
        if self.source == "library":
            return (f"{len(self.records)} readings for {self.query!r}, already in the "
                    f"library from {self.documents} documents.")
        if self.source == "read now":
            head = (f"{len(self.records)} readings for {self.query!r}, read from "
                    f"{self.documents} documents in {self.seconds/60:.0f} minutes. ")
            if self.contributed:
                return (head + "Nobody had read these before; they are in the "
                        "library now.")
            return head + "The readings were not added to the library."
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
        # The same scoping every other loader applies: a record with no place
        # of its own belongs to the place its file was read for. Flattening
        # without it made most of a town invisible to the very query that
        # wrote it -- the first live volunteer re-share of Ear Falls found 35
        # of its own 190 records, because 155 spec lines and plant readings
        # carry no place field of their own. Third appearance of the
        # loader-asymmetry family; same cure as the first two.
        file_place = payload.get("place")
        for record in payload.get("records") or []:
            out.append(scope_record_dict(record, file_place))
    return out


def _held(query: str, records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    want = query.strip().lower()
    return [r for r in records if want in str(r.get("place") or "").lower()]


def plan_documents(
    query: str,
    *,
    archive: Archive | None = None,
    max_documents: int = 20,
) -> list[dict[str, Any]]:
    """The documents a read of this place would work through, in reading order.

    One definition, shared by the installed reader (`ask`, below) and the
    in-browser reader's endpoints, so the two readers can never disagree about
    which documents a town's record is.

    Every document about this place, not just its water reports. This used to
    keep only titles containing "annual report" or "sewage treatment plant",
    which decided in advance that a place's record IS its sewage plant. The
    archive holds school board returns, hospital reports, assessment rolls and
    council minutes for the same towns, and a reader that filters them out can
    never surface them.

    Ordered so the densest sources are read first within the budget, because
    `max_documents` is a real limit and what it spends matters: recurring
    serials give comparable years; one-off documents give a single reading.
    Neither is excluded.
    """
    archive = archive or Archive()

    def _weight(item: dict[str, Any]) -> tuple[int, str]:
        title = str(item.get("title", "")).lower()
        recurring = 0 if ("annual report" in title or "report" in title) else 1
        return (recurring, title)

    return sorted(archive.iter_items(title_contains=query.lower()),
                  key=_weight)[:max_documents]


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
    items = plan_documents(query, archive=archive, max_documents=max_documents)

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
                # setdefault never fired here: to_dict always emits the place
                # key, so a record whose sentence named no place carried
                # place=None out of the reader. Loaders repair that from the
                # file header -- but a bundle pushed to another instance is
                # not a file with a header, so 151 of Ear Falls' 190 records
                # arrived at the live site nameless and invisible. Records
                # whose sentence names a DIFFERENT place (a Winnipeg
                # comparison figure in a Vancouver report) keep it.
                if not d.get("place"):
                    d["place"] = query
                # Only when the sentence did not name one. A page covering
                # four hospitals knows which is which; the title does not.
                d.setdefault("facility", None)
                if not d.get("facility"):
                    d["facility"] = facility
                if not d.get("period") and year:
                    d["period"] = year
                records.append(d)
                # Vocabulary gaps are collected and reported home. The person
                # asking is never shown them and never has to do anything about
                # them -- maintaining the vocabulary is our job, not theirs.
                if resolve_parameter(d.get("parameter") or "", d.get("unit")) is None:
                    unknown.add(str(d.get("parameter") or "").strip())

    # An empty bundle is not a contribution, and reaching the end of a read is
    # not success by itself.  Returning ``source="read now"`` here made the API
    # say "they are in the library now" even though there was nothing to verify
    # or write.  Preserve the attempted-document count, but make the outcome and
    # the absence of a side effect explicit.
    if not records:
        noun = "document" if len(items) == 1 else "documents"
        note = (f"No readings were recovered from {len(items)} matching {noun}; "
                "nothing was added to the library.")
        say(note)
        return Answer(
            query=query, source="empty", documents=len(items),
            seconds=time.time() - t0,
            unknown_parameters=sorted(unknown), note=note,
        )

    # Verify our own work before adding it to the shared library, on exactly the
    # same terms a stranger's contribution would be checked. Reading it yourself
    # is not a reason to trust it.
    bundle = make_bundle(records, contributor="local", note=query)
    verdict = verify_bundle(bundle, archive=archive)

    published = publish_supported(query, client.name, records, verdict, say=say)

    return Answer(
        query=query, records=records, source="read now",
        documents=len(items), seconds=time.time() - t0,
        verified=verdict.verified, published=published,
        contributed=published > 0,
        unknown_parameters=sorted(unknown),
    )


def publish_supported(
    query: str,
    model_name: str,
    records: list[dict[str, Any]],
    verdict: Any,
    *,
    say: Callable[[str], None] = lambda _m: None,
) -> int:
    """Write what the archive stood behind into the library. Returns how many.

    Publishes verdict.supported -- and ONLY that. Two defects lived on this
    write when it was inline in ask():

    * It stored `records`, the raw extraction, so readings whose page could
      not be retrieved at verify time ("nothing here is evidence") entered the
      library beside the verified ones. merge_bundle was explicitly fixed to
      merge only the supported set; this was the one write that still
      published everything on a bundle-level pass.
    * It gated on verdict.accepted, which one failed reading falsifies. The
      gold benchmark itself shows ~3% spurious extractions, so an hours-long
      read of a whole town was discarded for one hallucinated value -- while a
      stranger pushing the same records through /api/bundle would have had the
      good subset merged. The machine's own reads now get the same deal.
    """
    supported = list(getattr(verdict, "supported", None) or [])
    if not supported:
        if records:
            say(f"Verification failed on {len(verdict.failed)} readings and "
                "nothing survived; NOT added to the library. The readings are "
                "returned to you but not shared.")
        return 0

    LIBRARY.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-") or "place"
    payload = json.dumps({
        "place": query, "model": model_name, "n_records": len(supported),
        "verified": verdict.verified, "records": supported,
    }, indent=2, ensure_ascii=False)
    # Atomic against a reader mid-write; overwrite is intended -- a re-read
    # of the same place replaces its file.
    target = LIBRARY / f"{slug}.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, target)
    dropped = len(records) - len(supported)
    say(f"Verified {verdict.verified}/{verdict.total} readings against the "
        f"scans; {len(supported)} are in the library now"
        + (f", {dropped} failed their own evidence check and were not."
           if dropped else "."))
    return len(supported)
