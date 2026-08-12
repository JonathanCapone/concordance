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
    if _norm(claim.quote) not in _norm(text):
        return Standing(claim, False, "the quoted sentence is not on that page")

    state, why = _value_in_quote(claim.record.get("value"), claim.quote)
    if state == "ok":
        return Standing(claim, True, "sentence is on the page and the value is in it")
    if state == "unchecked":
        # A record with no number -- a conclusion, or a name. The sentence is
        # real, which is all that can be asked of it.
        return Standing(claim, True, f"sentence is on the page ({why})")

    if _value_in_damaged_quote(claim.record.get("value"), claim.quote):
        return Standing(claim, True,
                        "sentence is on the page and the value is in it once "
                        "OCR letter-for-digit damage is undone", )
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
