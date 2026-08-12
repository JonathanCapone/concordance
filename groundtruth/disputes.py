"""Let anyone correct anything, without anyone moderating anything.

The usual way to accept public contributions is to appoint people who decide
which ones are good. That is the part nobody wants to run, and it is also the
part that makes a project political: whoever holds the delete button holds the
record.

This avoids it with one rule applied to everybody equally:

    Every claim must cite a page and quote a sentence. The archive decides.

That rule already governs the machine's own output -- `contribute.verify_bundle`
checks that the quoted sentence really is on the page, and that the value really
is in the quoted sentence. Nothing about it is specific to a model. Point it at a
stranger's submission and it works the same way, because it never asks who is
speaking, only whether the paper says what they claim it says.

So the three things people want all become the same operation:

* **Adding a reading** -- submit a record with its page and quote. It is checked
  against the scan. No account, no reputation, no queue. If it verifies, it is
  in.
* **Correcting a reading** -- submit the correction with ITS page and quote. If
  the correction verifies and the original does not, the correction replaces it,
  automatically, with nobody in the loop.
* **Flagging a reading** -- say what is wrong. This is deliberately weaker than
  the other two, and the difference matters more than anything else here.

**An unevidenced flag never changes the data.** It is counted and shown -- "four
readers think this is wrong" is worth knowing -- but it cannot delete, hide or
outrank a record, because a claim with no evidence cannot beat a claim with
evidence without someone to adjudicate, and adjudication is the thing we are
refusing to build. To change what is shown, bring a page and a sentence.

**When two claims both verify, nobody wins.** They are shown side by side, both
marked contested, with both crops. This is the honest outcome for the failure
that verification genuinely cannot catch: "the average influent BOD was 104
mg/1" supports reading 104 as influent, and a careless reader filing it as
effluent quotes the same real sentence and passes every check. The machine has
no basis to prefer one. A reader looking at the two crops has an excellent one,
and settles it in about two seconds -- which is only possible because of
`citations`. The picture is what makes refusing to moderate a workable position
rather than a wish.

What this cannot do is stop someone patiently submitting a thousand
technically-verifiable misreadings. There is no mechanical defence against that
and this module does not pretend to one; it is named in the report.
"""

from __future__ import annotations

import collections
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .archive import Archive
from .contribute import _norm, _value_in_quote

#: What two claims have to share to be talking about the same thing.
#:
#: `facility` is here because Owen Sound's sewage plant and its water works are
#: both "Owen Sound", and merging them once made the town's record appear to run
#: twenty years longer than it does.
#:
#: `stream` is here because running this over the machine's own 781 records
#: filed Brantford's 1962 raw-sewage BOD of 210 ppm and its final-effluent BOD
#: of 10 ppm as the same measurement, and reported them as a contradiction. They
#: are not in contradiction; they are the influent and the effluent, which is
#: the entire point of a treatment plant. Without this the ledger manufactures
#: disputes out of the plant working.
SLOT_FIELDS = ("place", "facility", "parameter", "unit", "period", "stream")


def slot_of(record: dict[str, Any]) -> str:
    """The thing a claim is an assertion *about*."""
    return "|".join(str(record.get(f) or "").strip().lower() for f in SLOT_FIELDS)


@dataclass
class Claim:
    """One assertion, from anybody, about one measurement."""

    record: dict[str, Any]
    source: str = "extraction"        # extraction | person | correction
    contributor: str = "anonymous"
    disputes: str = ""                # id of a claim this contests
    note: str = ""                    # why, in the contributor's own words

    @property
    def id(self) -> str:
        prov = self.record.get("provenance") or {}
        raw = json.dumps({
            "i": prov.get("identifier"), "p": prov.get("page"),
            "q": (prov.get("source_text") or "")[:200],
            "v": repr(self.record.get("value")),
            "k": slot_of(self.record),
        }, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @property
    def slot(self) -> str:
        return slot_of(self.record)

    @property
    def quote(self) -> str:
        return str((self.record.get("provenance") or {}).get("source_text") or "")

    @property
    def has_evidence(self) -> bool:
        prov = self.record.get("provenance") or {}
        return bool(prov.get("identifier") and prov.get("page") and self.quote)


@dataclass
class Flag:
    """Someone thinks a claim is wrong, and has not shown why.

    Kept apart from Claim on purpose. Merging them would make it possible for an
    assertion with no evidence to outrank one with evidence, which is exactly
    the situation that requires a moderator.
    """

    claim_id: str
    reason: str = ""
    contributor: str = "anonymous"

    def to_dict(self) -> dict[str, Any]:
        return {"claim_id": self.claim_id, "reason": self.reason[:400],
                "contributor": self.contributor}


@dataclass
class Standing:
    """What the archive says about one claim."""

    claim: Claim
    verified: bool
    why: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.claim.id, "verified": self.verified, "why": self.why,
            "source": self.claim.source, "contributor": self.claim.contributor,
            "value": self.claim.record.get("value"),
            "unit": self.claim.record.get("unit"),
            "parameter": self.claim.record.get("parameter"),
            "quote": self.claim.quote[:220],
            "note": self.claim.note[:300],
        }


#: How the vision path writes a cell reference: "table cell [row / column]".
# Imported, not redefined. Two copies of "what a table citation looks like"
# is two chances to disagree, and the bundle path and the ledger path
# disagreeing about exactly that is what refused all 535 vision records.
from .contribute import CELL_RE  # noqa: E402


def _check_cell(claim: Claim, cell: Any, text: str) -> Standing:
    """Verify a table reading, which has headings instead of a sentence.

    Two questions, chosen to mirror the prose check as closely as the medium
    allows: are the cited headings on the page, and does the value appear in the
    page's digits. Neither is as strong as quoting a sentence, and the standing
    says so in words rather than pretending otherwise.

    Headings are judged by the vision path's own rule, which lets a page whose
    OCR can find nothing at all abstain rather than refuse. A table whose text
    layer was destroyed is precisely the case that path exists for, and its
    silence is a fact about the scanner.
    """
    from .vision import _label_on_page, _page_can_referee

    labels = [part.strip() for part in cell.group(1).split("/") if part.strip()]
    claimed = [{"row_label": labels[0] if labels else "",
                "column_label": labels[1] if len(labels) > 1 else ""}]

    if _page_can_referee(claimed, text):
        missing = [lab for lab in labels if not _label_on_page(lab, text)]
        if missing:
            return Standing(claim, False,
                            "the table headings cited are not on that page: "
                            + ", ".join(repr(m) for m in missing))
        heading_note = "the table headings are on the page"
    else:
        heading_note = ("the page's OCR is too damaged to confirm or refute the "
                        "headings, which is the case this path exists for")

    if claim.record.get("value") is None:
        return Standing(claim, True, f"{heading_note}; no value to check")
    if _value_in_damaged_quote(claim.record.get("value"), text):
        return Standing(claim, True, f"{heading_note}, and the value is in its digits")
    return Standing(claim, False,
                    f"{heading_note}, but the value does not appear anywhere in "
                    "the page's digits")


def check(claim: Claim, *, archive: Archive | None = None,
          pages: dict[str, dict[int, str]] | None = None) -> Standing:
    """Ask the paper, not the person.

    Two questions, the same two the machine's own output has to answer: is that
    sentence on that page, and is that value in that sentence. Nothing here
    depends on who submitted it, which is the entire reason this can be open.
    """
    if not claim.has_evidence:
        return Standing(claim, False, "no page or no quoted sentence")

    prov = claim.record.get("provenance") or {}
    ident, page_no = str(prov.get("identifier")), prov.get("page")

    cache = pages if pages is not None else {}
    if ident not in cache:
        try:
            cache[ident] = {p.page: p.text for p in (archive or Archive()).pages(ident)}
        except Exception as exc:  # noqa: BLE001
            return Standing(claim, False, f"page not retrievable: {str(exc)[:60]}")

    text = cache[ident].get(page_no, "")
    if not text:
        return Standing(claim, False, "page not retrievable")

    # A reading off a table image cannot be checked the same way, and treating
    # it as though it could would mark the entire table dataset unsupported.
    # Its evidence is not a sentence -- a table has none -- but a cell
    # reference, "table cell [Jan. / MAX. DAILY Flow]", and the thing to verify
    # is that those headings are on the page and the value is in its digits.
    cell = CELL_RE.match(claim.quote.strip())
    if cell:
        return _check_cell(claim, cell, text)

    if _norm(claim.quote) not in _norm(text):
        return Standing(claim, False, "the quoted sentence is not on that page")

    state, why = _value_in_quote(claim.record.get("value"), claim.quote)
    if state == "ok":
        # `why` is empty when the sentence states the value outright, and
        # otherwise names the allowance that was made. Carrying it into the
        # ledger keeps the distinction visible instead of flattening every
        # verified record into one word.
        note = "sentence is on the page and the value is in it"
        return Standing(claim, True, f"{note} {why}".strip() if why else note)
    if state == "unchecked":
        # A record with no number -- a conclusion, or a name. The sentence is
        # real, which is all that can be asked of it.
        return Standing(claim, True, f"sentence is on the page ({why})")

    # No damaged-quote fallback here any more: _value_in_quote undoes the
    # scanner's letter-for-digit damage itself, and says so in `why`. It used to
    # live only on this path, which meant a reading the LEDGER verified was
    # REFUSED when the same reading arrived in a bundle -- the two checks that
    # are supposed to be the same check disagreeing about the same record.
    # _value_in_damaged_quote is still used by the table-cell path above.
    return Standing(claim, False, why)


#: Glyphs 1960s scanners routinely read as letters. Every one of these was found
#: in the real record: "I5 feet deep" for 15, "3I per cent" for 31, "SOfo" for
#: 50%.
_OCR_DIGITS = str.maketrans({
    "I": "1", "l": "1", "|": "1", "i": "1",
    "O": "0", "o": "0", "Q": "0", "D": "0",
    "S": "5", "s": "5", "Z": "2", "z": "2",
    "B": "8", "G": "6", "g": "9", "T": "7", "A": "4",
})


def _value_in_damaged_quote(value: Any, quote: str) -> bool:
    """Is the value in the sentence, once the scanner's letters are read as digits?

    Needed because the strict check convicts the extractor of the scanner's
    crime. "Each pass of the aeration tanks is 30 feet wide, I5 feet deep" holds
    the digits 3-0-5-2-0-0 as far as a literal reading is concerned, so a
    perfectly correct depth of 15 was rejected as unsupported. Three of the 29
    unsupported slots in the first real run were this, and throwing away right
    answers is not a conservative failure -- it is the same silent data loss the
    project exists to reverse.

    This cannot be used to smuggle anything in. The sentence still has to be on
    the page, letter for letter; all that is relaxed is how its own characters
    are read. An attacker gains only what the scan already ambiguously contains.
    """
    if value is None:
        return False
    text = str(quote or "").translate(_OCR_DIGITS)
    digits = "".join(c for c in text if c.isdigit())
    if not digits:
        return False
    for form in _forms(value):
        if form and form in digits:
            return True
    return False


def _forms(value: Any) -> list[str]:
    """The ways a number can appear once punctuation and scale are stripped."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return []
    out = {repr(number), f"{number:f}", str(value)}
    if number.is_integer():
        out.add(str(int(number)))
    return ["".join(c for c in s if c.isdigit()).lstrip("0") or "0" for s in out]


@dataclass
class Slot:
    """Every claim about one measurement, and where that leaves it."""

    key: str
    standings: list[Standing] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)

    @property
    def surviving(self) -> list[Standing]:
        return [s for s in self.standings if s.verified]

    @property
    def rejected(self) -> list[Standing]:
        return [s for s in self.standings if not s.verified]

    @property
    def values(self) -> list[Any]:
        out, seen = [], set()
        for s in self.surviving:
            v = s.claim.record.get("value")
            k = repr(v)
            if k not in seen:
                seen.add(k)
                out.append(v)
        return out

    @property
    def state(self) -> str:
        if not self.surviving:
            return "unsupported"
        if len(self.values) > 1:
            return "contested"
        return "settled"

    @property
    def same_sentence(self) -> bool:
        """Do the competing claims read the SAME sentence differently?

        Worth separating, because it says what kind of disagreement this is. Two
        readings of one sentence is an ambiguity in the document -- "the average
        influent BOD and suspended solids were 104 mg/1 and 224 mg/1
        respectively" can be got the wrong way round by anyone. Two different
        sentences is a disagreement about which evidence applies, which is a
        different argument and often means the slot key is too coarse.
        """
        quotes = {_norm(s.claim.quote) for s in self.surviving}
        return len(quotes) == 1 and len(self.values) > 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.key, "state": self.state,
            "values": self.values,
            "same_sentence": self.same_sentence,
            "surviving": [s.to_dict() for s in self.surviving],
            "rejected": [s.to_dict() for s in self.rejected],
            "flags": [f.to_dict() for f in self.flags],
            "n_flags": len(self.flags),
        }


@dataclass
class Ledger:
    """The state of every disputed and undisputed measurement."""

    slots: dict[str, Slot] = field(default_factory=dict)

    def settled(self) -> list[Slot]:
        return [s for s in self.slots.values() if s.state == "settled"]

    def contested(self) -> list[Slot]:
        return [s for s in self.slots.values() if s.state == "contested"]

    def unsupported(self) -> list[Slot]:
        return [s for s in self.slots.values() if s.state == "unsupported"]

    def most_flagged(self, limit: int = 20) -> list[dict[str, Any]]:
        """Where readers disagree with the record but have not shown why.

        Not an action queue. Nobody works through this list, because working
        through it would be moderating. It is a map of where the data looks
        wrong to people, which is useful for deciding what to re-read -- and
        re-reading produces evidence, which is the only thing that changes
        anything.
        """
        flagged = [s for s in self.slots.values() if s.flags]
        flagged.sort(key=lambda s: -len(s.flags))
        return [{"slot": s.key, "flags": len(s.flags), "state": s.state,
                 "values": s.values,
                 "reasons": [f.reason[:120] for f in s.flags[:4]]}
                for s in flagged[:limit]]

    def report(self) -> dict[str, Any]:
        by_source: collections.Counter = collections.Counter()
        for slot in self.slots.values():
            for s in slot.surviving:
                by_source[s.claim.source] += 1
        return {
            "slots": len(self.slots),
            "settled": len(self.settled()),
            "contested": len(self.contested()),
            "unsupported": len(self.unsupported()),
            "surviving_claims_by_source": dict(by_source),
            "flags": sum(len(s.flags) for s in self.slots.values()),
            "most_flagged": self.most_flagged(),
            "not_measured": NOT_MEASURED,
        }


#: Said out loud in the output, because a verification badge invites being read
#: as a correctness badge.
NOT_MEASURED = [
    "Whether a verified reading is the RIGHT reading. 'The average influent BOD "
    "and suspended solids were 104 mg/1 and 224 mg/1 respectively' supports "
    "filing 104 as influent, and filing it as effluent quotes the same real "
    "sentence and passes every check. That is why contested slots show both "
    "crops instead of choosing.",
    "Whether a contributor is acting in good faith. There is no mechanical "
    "defence against someone patiently submitting many technically-verifiable "
    "misreadings, and this does not pretend to one.",
    "Anything about a flag except that somebody raised it. Flags carry no "
    "evidence by definition, so they are counted and shown and never acted on.",
]


def resolve(
    claims: Iterable[Claim],
    flags: Iterable[Flag] = (),
    *,
    archive: Archive | None = None,
) -> Ledger:
    """Check every claim and group them by what they are about.

    Order does not matter and neither does who arrived first. A record extracted
    by the machine and a record typed in by a stranger are the same kind of
    thing here, and are checked identically -- which is the property that makes
    the whole arrangement possible.
    """
    ledger = Ledger()
    pages: dict[str, dict[int, str]] = {}
    by_id: dict[str, Slot] = {}

    for claim in claims:
        standing = check(claim, archive=archive, pages=pages)
        slot = ledger.slots.setdefault(claim.slot, Slot(key=claim.slot))
        slot.standings.append(standing)
        by_id[claim.id] = slot

    for flag in flags:
        slot = by_id.get(flag.claim_id)
        if slot is not None:
            slot.flags.append(flag)
    return ledger


def load_claims(directory: str | Path = "data/results") -> list[Claim]:
    """Every record on disk, as claims by the machine.

    The extractor's output enters the ledger on exactly the same footing as a
    stranger's submission. It gets no standing for having been produced by this
    project.
    """
    skip = {"gold_report", "metadata_proposals", "silence_report", "corpus_census",
            "audit", "cost_model", "vocab_proposals", "frontier", "vision_trial",
            "vision_trial_corpus"}
    out: list[Claim] = []
    for path in Path(directory).glob("*.json"):
        if path.stem in skip:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for record in payload.get("records") or []:
            out.append(Claim(record=record, source="extraction",
                             contributor=str(payload.get("model") or "extraction")))
    return out


# --------------------------------------------------------------------------
# submitting one, as a person
# --------------------------------------------------------------------------

#: Where contributions land. A separate file per contributor keeps the
#: machine's output and people's submissions distinguishable on disk without
#: giving either one precedence when they are read back -- `load_claims` and
#: `load_contributions` both produce plain Claims, and `check` cannot tell them
#: apart.
CONTRIBUTIONS = Path("data/contributions")


@dataclass
class Submission:
    """What happened when somebody offered a reading."""

    standing: Standing
    stored: bool
    where: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = self.standing.to_dict()
        d["accepted"] = self.standing.verified
        d["stored"] = self.stored
        d["where"] = self.where
        d["what_happens_now"] = (
            "It is in the record, on the same footing as everything else. If it "
            "disagrees with an existing reading that also checks out, both are "
            "shown with a picture of the sentence each came from, and nobody "
            "decides between them."
            if self.standing.verified else
            "It is not in the record, and nothing was deleted. The archive did "
            "not support it: " + self.standing.why + ". Nobody rejected this -- "
            "the page did."
        )
        return d


def submit(
    record: dict[str, Any],
    *,
    contributor: str = "anonymous",
    note: str = "",
    disputes: str = "",
    archive: Archive | None = None,
    directory: str | Path = CONTRIBUTIONS,
) -> Submission:
    """Offer a reading. The archive accepts or refuses it; no one reviews it.

    There is no queue, no account and no reputation, because none of those would
    add anything: the check does not consult them. A submission that cites a real
    sentence containing its own value is in, and one that does not is out, and
    both outcomes are decided by the same code that judges the machine's output.

    What a person can do that the machine cannot is disagree usefully. A reading
    that contests an existing one is stored exactly like any other and surfaces
    as a contested measurement, which is the honest state for two claims the
    paper supports equally well.
    """
    claim = Claim(record=record, source="correction" if disputes else "person",
                  contributor=contributor or "anonymous", note=note, disputes=disputes)
    standing = check(claim, archive=archive)
    if not standing.verified:
        return Submission(standing, stored=False)

    path = Path(directory) / f"{claim.id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "claim_id": claim.id, "contributor": claim.contributor,
        "source": claim.source, "note": claim.note, "disputes": claim.disputes,
        "verified_because": standing.why,
        "records": [record],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return Submission(standing, stored=True, where=str(path))


def load_contributions(directory: str | Path = CONTRIBUTIONS) -> list[Claim]:
    """Every reading a person has submitted, as claims.

    Read back on exactly the same footing as the machine's own. Nothing here
    records who to believe, because nothing in this design ever asks.
    """
    out: list[Claim] = []
    directory = Path(directory)
    if not directory.exists():
        return out
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for record in payload.get("records") or []:
            out.append(Claim(
                record=record,
                source=str(payload.get("source") or "person"),
                contributor=str(payload.get("contributor") or "anonymous"),
                note=str(payload.get("note") or ""),
                disputes=str(payload.get("disputes") or ""),
            ))
    return out


def load_vision_records(
    path: str | Path = "data/results/vision_trial_corpus.json",
) -> list[Claim]:
    """Table readings, as claims on the same footing as everything else.

    Kept as its own loader because the trial writes a page-keyed file rather
    than a flat record list, not because table readings deserve different
    treatment. `check()` judges them by their headings and the page's digits,
    which is the closest the medium allows to quoting a sentence, and nothing
    downstream is told which path a record came from.
    """
    out: list[Claim] = []
    p = Path(path)
    if not p.exists():
        return out
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return out
    for row in rows.values():
        if not isinstance(row, dict) or "error" in row:
            continue
        for record in row.get("records") or []:
            out.append(Claim(record=record, source="extraction",
                             contributor="vision"))
    return out
