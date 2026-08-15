"""Who proposed what, who backed it, and how everyone voted.

The rest of this project recovers measurements -- a number, a unit, a place, a
year. This recovers a different kind of fact, and the archive is full of it:
**decisions, and the people who made them.**

    "It was moved by Alderman Eisenberger and seconded by Alderman Morelli that
    the Building Commissioner be authorized to issue a demolition permit for
    336-338 Jackson Street West ... CARRIED."

    "Recorded vote. YEAS: Mayor Morrow, Aldermen Cooke, Kiss, Agro, McCulloch,
    Morelli, Copps, Wilson, Agostino, Eisenberger, Charters, Jackson, Merling,
    Anderson, D'Amico, Ross. -16. NAYS: -0."

That is a complete municipal roll call from 1992, naming sixteen people and how
each of them voted, sitting in a scanned volume nobody has opened. Deliberative
records -- minutes, agendas, hansard, committee reports, royal commission
hearings -- are 13,604 items, 13.1% of this collection, and they were the single
category most damaged by the router bug fixed alongside this module, because
minutes have always been set in narrow columns.

**The spine of this is deterministic on purpose.** "It was moved by X and
seconded by Y that Z. CARRIED." is a form that has barely changed in a century,
and a regular expression that finds it can be checked by a person in a way a
model's answer cannot. No GPU, no cost, no hallucination surface. A model is
useful for summarising what a motion was *about*; it is not needed to learn who
moved it, and using one there would trade a verifiable fact for a plausible one.

What this deliberately does NOT claim: that a motion which carried was ever
carried out. A resolution is a promise, and whether the demolition happened, the
rent stayed at $357, or the study was ever published lives in a different
document -- often years later, often in a different agency. That gap is the
interesting part, and `frontier.py` is where it belongs: a carried motion is a
question with a known prerequisite. Recording a promise as an outcome would be
the same error as charting a design specification as a measurement.
"""

from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from .models import PageText, Provenance

#: Titles that mark a person in these records. Ordered longest-first so
#: "Deputy Mayor" is not read as "Mayor".
ROLES = [
    "Deputy Mayor", "Acting Mayor", "Mayor", "Reeve", "Deputy Reeve", "Warden",
    "Alderman", "Aldermen", "Alderwoman", "Councillor", "Councilman",
    "Controller", "Chairman", "Chairwoman", "Chair", "Commissioner",
    "Trustee", "Treasurer", "Clerk", "Solicitor", "Engineer",
    "Hon.", "Mr.", "Mrs.", "Miss", "Ms.", "Dr.",
]
_ROLE_ALT = "|".join(re.escape(r) for r in ROLES)

#: A surname as OCR leaves it. Apostrophes come back as any of several
#: characters -- "D'Amico" has been seen as "D�Amico", "D'Amico" and "DAmico" in
#: one volume -- so the class is wide and normalisation happens afterwards.
#:
#: The `(?-i:...)` matters more than it looks. These patterns need re.I for
#: "moved by" / "IT WAS MOVED BY", but under that flag `[A-Z]` also matches
#: lowercase, so the seconder in "seconded by Alderman Kiss that the report be
#: adopted" parsed as a person named "Kiss that" -- who then appeared in the
#: ledger 26 times as the council's second most active member. Capitalisation is
#: the only thing separating a surname from an ordinary word here, so the name
#: class turns case-sensitivity back on for itself.
_SURNAME = r"(?-i:[A-Z][A-Za-z‘’'´`�.-]{1,24})"

MOTION_RE = re.compile(
    rf"(?:it\s+was\s+)?moved\s+by\s+(?:(?:{_ROLE_ALT})\s+)?({_SURNAME}(?:\s+{_SURNAME})?)"
    rf"\s*,?\s*and\s+seconded\s+by\s+(?:(?:{_ROLE_ALT})\s+)?({_SURNAME}(?:\s+{_SURNAME})?)"
    rf"\s*,?\s*(?:that\s+)?(.{{0,900}}?)"
    rf"(?=\b(?:CARRIED|DEFEATED|LOST|WITHDRAWN|DEFERRED|TABLED)\b|"
    rf"(?:it\s+was\s+)?moved\s+by\s|\Z)",
    re.I | re.S,
)

OUTCOME_RE = re.compile(
    r"\b(CARRIED|DEFEATED|LOST|WITHDRAWN|DEFERRED|TABLED|REFERRED BACK)\b", re.I)

#: Where the search for an outcome has to give up: the next proposal.
NEXT_MOTION_RE = re.compile(r"(?:it\s+was\s+)?moved\s+by\s", re.I)

#: A recorded division is written as a run of labelled lists -- "YEAS: Mayor
#: Morrow, Aldermen Cooke, Kiss ... -16. NAYS: -0." -- and the trailing count is
#: the clerk's own tally. That count is the control: if the names parsed do not
#: add up to it, the roll was misread, and the report says so rather than
#: publishing a division quietly missing two people.
#:
#: Found by scanning for labels and bounding each span, not by one large
#: expression. The expression version broke on "NAYS: �-0." -- a speck of
#: scanner dirt before the tally -- and the empty NAYS list then ran on and
#: swallowed the following paragraph, so twelve councillors who had voted in
#: favour were recorded as voting against. 17 of 47 divisions were wrong that
#: way, and only the tally caught it.
ROLL_LABEL_RE = re.compile(r"\b(YEAS?|NAYS?|ABSTAIN(?:ED|TIONS)?|ABSENT)\b\s*[:.]?", re.I)

#: Where a roll must stop, whatever comes after.
ROLL_STOP_RE = re.compile(
    r"\b(CARRIED|DEFEATED|LOST|WITHDRAWN|DEFERRED|TABLED|moved\s+by|"
    r"Recorded\s+vote)\b", re.I)

#: The clerk's tally at the end of a list. Junk on either side is tolerated
#: because scans put marks there -- "�-0. * " is one real example, and an
#: anchored pattern that insisted on clean whitespace failed to find the count
#: at all, which silently disarmed the only control this module has.
ROLL_COUNT_RE = re.compile(r"[-—–]\s*(\d+)\s*[^A-Za-z0-9]{0,6}$")

#: Beyond this many characters a "list of names" is prose that happens to follow
#: the word "absent". Real rolls on a full council run to about 200 characters.
MAX_ROLL_CHARS = 400

_CAST = {"yea": "yea", "yeas": "yea", "nay": "nay", "nays": "nay",
         "abstain": "abstain", "abstained": "abstain", "abstentions": "abstain",
         "absent": "absent"}

_APOSTROPHES = str.maketrans({"‘": "'", "’": "'", "´": "'",
                              "`": "'", "�": "'"})

#: Words that turn up where a surname is expected and are not people.
_NOT_A_NAME = {
    "the", "that", "this", "council", "committee", "report", "section", "city",
    "board", "motion", "resolution", "amendment", "and", "seconded", "moved",
    "his", "her", "worship", "same", "none", "nil", "carried", "defeated",
}


def clean_name(raw: str) -> str:
    """Normalise a name as OCR left it, without inventing a spelling.

    Only mechanical repairs: apostrophe variants folded, trailing punctuation
    dropped, whitespace collapsed. Guessing that "Eisenherger" means
    "Eisenberger" is a judgement, and judgements about identity belong with a
    person -- the same rule the vocabulary follows.
    """
    t = str(raw or "").translate(_APOSTROPHES)
    t = re.sub(r"\s+", " ", t).strip(" .,;:")
    return t


def _plausible(name: str) -> bool:
    t = clean_name(name)
    if len(t) < 2 or t.lower() in _NOT_A_NAME:
        return False
    # A surname is mostly letters. OCR noise is mostly not.
    letters = sum(c.isalpha() for c in t)
    return letters >= 2 and letters / len(t) >= 0.6


@dataclass
class Vote:
    """One person's recorded position on one motion."""

    person: str
    cast: str          # yea | nay | abstain | absent

    def to_dict(self) -> dict[str, Any]:
        return {"person": self.person, "cast": self.cast}


@dataclass
class Roll:
    """A recorded division, and whether it adds up.

    The clerk wrote the count down. If the names we parsed disagree with it, the
    roll was misread, and that has to be visible rather than smoothed over -- a
    vote list quietly missing two people is exactly the kind of plausible wrong
    answer this project keeps finding in itself.
    """

    cast: str
    people: list[str] = field(default_factory=list)
    stated_count: int | None = None

    @property
    def agrees(self) -> bool:
        """Do the names match the tally the clerk wrote?

        True when there is no tally, because nothing has been contradicted --
        but that is NOT the same as having been checked, and `checked` is what
        callers must consult before reporting this as verification. Roughly
        four fifths of rolls in this corpus carry no tally at all, so a control
        that reports those as agreeing is a control that passes when there is
        nothing to check. This project has built five of those.
        """
        return self.stated_count is None or len(self.people) == self.stated_count

    @property
    def checked(self) -> bool:
        """Was there a clerk's tally to check the names against?"""
        return self.stated_count is not None

    def to_dict(self) -> dict[str, Any]:
        return {"cast": self.cast, "people": self.people,
                "stated_count": self.stated_count, "counts_agree": self.agrees,
                "checked": self.checked}


@dataclass
class Motion:
    """Something proposed, and what happened to it."""

    text: str
    moved_by: str
    seconded_by: str
    outcome: str = "unrecorded"
    rolls: list[Roll] = field(default_factory=list)
    body: str = ""
    date: str = ""
    provenance: Provenance | None = None

    @property
    def votes(self) -> list[Vote]:
        return [Vote(p, r.cast) for r in self.rolls for p in r.people]

    @property
    def recorded(self) -> bool:
        return bool(self.rolls)

    @property
    def unanimous(self) -> bool | None:
        if not self.recorded:
            return None
        against = sum(len(r.people) for r in self.rolls if r.cast == "nay")
        return against == 0

    @property
    def rolls_agree(self) -> bool:
        """Every division reconciles with the count the clerk wrote."""
        return all(r.agrees for r in self.rolls)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "moved_by": self.moved_by,
            "seconded_by": self.seconded_by,
            "outcome": self.outcome,
            "body": self.body,
            "date": self.date,
            "recorded_vote": self.recorded,
            "unanimous": self.unanimous,
            "rolls_agree": self.rolls_agree,
            "rolls": [r.to_dict() for r in self.rolls],
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }


# --------------------------------------------------------------------------
# reading a page
# --------------------------------------------------------------------------

def _split_names(blob: str) -> list[str]:
    """Pull the surnames out of a roll.

    The clerk writes "Mayor Morrow, Aldermen Cooke, Kiss, Agro, ... Ross" -- one
    title, then a run of bare surnames. Splitting on commas and stripping any
    leading title handles both the titled first entry and the untitled rest.
    """
    blob = re.sub(rf"\b({_ROLE_ALT})\b", " ", blob, flags=re.I)
    out = []
    for part in re.split(r"[,;]|\band\b", blob):
        name = clean_name(part)
        if name and _plausible(name):
            out.append(name)
    return out


def _cast_of(label: str) -> str:
    t = label.lower().strip(": .")
    return _CAST.get(t) or _CAST.get(t.rstrip("s")) or "yea"


def _scan_rolls(text: str) -> list[tuple[Roll, int, int]]:
    """Every labelled vote list in the text, with where it starts and ends.

    Each span runs from its own label to whichever comes first: the next label,
    an outcome word, or the character cap. Bounding it is the whole point -- an
    unbounded list is how an empty NAYS came to contain the entire next motion.
    """
    labels = list(ROLL_LABEL_RE.finditer(text))
    out: list[tuple[Roll, int, int]] = []
    for i, m in enumerate(labels):
        start = m.end()
        end = labels[i + 1].start() if i + 1 < len(labels) else len(text)
        end = min(end, start + MAX_ROLL_CHARS)
        stop = ROLL_STOP_RE.search(text, start, end)
        if stop:
            end = stop.start()

        span = text[start:end].strip()
        cm = ROLL_COUNT_RE.search(span)
        stated = int(cm.group(1)) if cm else None
        if cm:
            span = span[: cm.start()]
        out.append((Roll(cast=_cast_of(m.group(1)),
                         people=_split_names(span),
                         stated_count=stated),
                    m.start(), end))
    return out


def _rolls_in(text: str) -> list[Roll]:
    return [r for r, _, _ in _scan_rolls(text)]


DATE_RE = re.compile(
    r"\b(1[6-9]\d\d|20[0-2]\d)\s+"
    r"(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(\d{1,2})\b", re.I)


#: What a standalone division was about. Recorded votes in these volumes hang
#: off a committee report section rather than a "moved by" clause -- "Section 7
#: Re: Promotional Banner Across Main Street West ... Recorded vote. YEAS: ..."
#: -- so the subject is whatever the clerk wrote after "Re:".
SUBJECT_RE = re.compile(r"\bRe\s*:\s*(.{4,220}?)(?=\s*(?:Recorded vote|YEAS?\s*:|\Z))",
                        re.I | re.S)


def read_page(
    page: PageText,
    *,
    body: str = "",
    year: str = "",
) -> list[Motion]:
    """Recover every motion and every recorded division stated on one page.

    Works on the flattened page text because a motion routinely runs across a
    column break, and the line structure that matters elsewhere in this project
    is noise here.

    Divisions are found independently of motions rather than only inside them.
    Attaching a roll to the nearest "moved by" clause found 50 motions and zero
    votes in a volume holding 40 recorded divisions, because most of them belong
    to a committee report section that no one formally moved on the page. A
    recorded vote with no mover is still sixteen people going on the record.
    """
    text = " ".join(page.text.split())
    date = ""
    dm = DATE_RE.search(text)
    if dm:
        date = f"{dm.group(1)}-{dm.group(2)[:3]}-{int(dm.group(3)):02d}"

    motions: list[tuple[int, Motion]] = []
    claimed: list[tuple[int, int]] = []

    for m in MOTION_RE.finditer(text):
        mover, seconder, body_text = m.group(1), m.group(2), m.group(3)
        if not (_plausible(mover) and _plausible(seconder)):
            continue
        # Look just past the motion for its outcome and any division, and stop
        # at the next proposal. Without that stop, a motion whose result was
        # never written down borrows the following motion's -- so a resolution
        # nobody recorded a decision on is published as DEFEATED.
        tail = text[m.end(): m.end() + 700]
        nxt = NEXT_MOTION_RE.search(tail)
        if nxt:
            tail = tail[: nxt.start()]
        outcome_m = OUTCOME_RE.search(tail)
        outcome = outcome_m.group(1).lower() if outcome_m else "unrecorded"
        window = tail[: outcome_m.end()] if outcome_m else tail
        rolls = _rolls_in(window)
        if rolls:
            claimed.append((m.end(), m.end() + len(window)))

        motions.append((m.start(), Motion(
            text=clean_name(body_text)[:900],
            moved_by=clean_name(mover),
            seconded_by=clean_name(seconder),
            outcome=outcome,
            rolls=rolls,
            body=body,
            date=date or year,
            provenance=Provenance(
                identifier=page.identifier,
                page=page.page,
                source_text=text[m.start(): m.end() + (outcome_m.end() if outcome_m else 0)][:1200],
            ),
        )))

    motions.extend(_standalone_divisions(text, claimed, page=page,
                                         body=body, date=date or year))
    # Document order, not motions-then-divisions. A page's decisions read in the
    # order they were taken, which is how anyone checking against the scan will
    # look for them.
    motions.sort(key=lambda pair: pair[0])
    return [m for _, m in motions]


def _standalone_divisions(
    text: str,
    claimed: list[tuple[int, int]],
    *,
    page: PageText,
    body: str,
    date: str,
) -> list[tuple[int, Motion]]:
    """Recorded votes that belong to no motion on this page.

    Kept as motions with no mover rather than as a separate type: the thing that
    matters about both is that named people went on the record about a named
    subject, and splitting them would mean every question about a person's
    voting history had to ask twice.
    """
    out: list[tuple[int, Motion]] = []
    last_end = -1
    for roll, start, end in _scan_rolls(text):
        if any(lo <= start < hi for lo, hi in claimed):
            continue

        # "YEAS: ... -16. NAYS: -0." is ONE division written as two rolls. A gap
        # this small cannot be a new question, so they join rather than becoming
        # two decisions with contradictory outcomes.
        if out and 0 <= start - last_end <= 40:
            out[-1][1].rolls.append(roll)
            last_end = end
            continue

        head = text[max(0, start - 400): start]
        subjects = SUBJECT_RE.findall(head)
        subject = clean_name(subjects[-1]) if subjects else ""
        outcome_m = OUTCOME_RE.search(text[end: end + 200])
        out.append((start, Motion(
            text=subject[:400] or "(recorded division, subject not stated on page)",
            moved_by="", seconded_by="",
            outcome=outcome_m.group(1).lower() if outcome_m else "unrecorded",
            rolls=[roll], body=body, date=date,
            provenance=Provenance(identifier=page.identifier, page=page.page,
                                  source_text=text[max(0, start - 260): end + 60][:1200]),
        )))
        last_end = end
    return out


# --------------------------------------------------------------------------
# the people
# --------------------------------------------------------------------------

@dataclass
class Person:
    """Someone who appears in the record, and what they were seen doing."""

    name: str
    roles: collections.Counter = field(default_factory=collections.Counter)
    bodies: set[str] = field(default_factory=set)
    moved: int = 0
    seconded: int = 0
    votes: collections.Counter = field(default_factory=collections.Counter)
    first_seen: str = ""
    last_seen: str = ""
    documents: set[str] = field(default_factory=set)

    @property
    def appearances(self) -> int:
        return self.moved + self.seconded + sum(self.votes.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "roles": [r for r, _ in self.roles.most_common()],
            "bodies": sorted(self.bodies),
            "moved": self.moved,
            "seconded": self.seconded,
            "votes": dict(self.votes),
            "appearances": self.appearances,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "documents": sorted(self.documents),
        }


@dataclass
class Ledger:
    """Everyone found, and every motion they touched."""

    people: dict[str, Person] = field(default_factory=dict)
    motions: list[Motion] = field(default_factory=list)

    def _person(self, name: str) -> Person:
        key = name.lower()
        p = self.people.get(key)
        if p is None:
            p = self.people[key] = Person(name=name)
        return p

    def add(self, motions: Iterable[Motion], *, roles_from: str = "") -> None:
        seen_roles = collections.Counter(
            re.findall(rf"\b({_ROLE_ALT})\s+({_SURNAME})", roles_from or "", re.I))
        for role, surname in seen_roles:
            if _plausible(surname):
                self._person(clean_name(surname)).roles[role.title().rstrip("men") + "man"
                                                        if role.lower() == "aldermen"
                                                        else role.title()] += 1

        for m in self.motions_of(motions):
            self.motions.append(m)
            for name, field_ in ((m.moved_by, "moved"), (m.seconded_by, "seconded")):
                if not name:
                    continue
                p = self._person(name)
                setattr(p, field_, getattr(p, field_) + 1)
                self._stamp(p, m)
            for v in m.votes:
                p = self._person(v.person)
                p.votes[v.cast] += 1
                self._stamp(p, m)

    @staticmethod
    def motions_of(motions: Iterable[Motion]) -> list[Motion]:
        """Anything that records a decision: a proposal, or a division, or both.

        A recorded vote with no mover named on the page is still sixteen people
        going on the record, and requiring a mover would have discarded every
        one of the 40 divisions in the first volume tested.
        """
        return [m for m in motions
                if (m.moved_by and m.seconded_by) or m.rolls]

    def _stamp(self, p: Person, m: Motion) -> None:
        if m.body:
            p.bodies.add(m.body)
        if m.provenance:
            p.documents.add(m.provenance.identifier)
        d = m.date or ""
        if d:
            p.first_seen = min(p.first_seen or d, d)
            p.last_seen = max(p.last_seen or d, d)

    # -- questions worth asking -------------------------------------------

    def most_active(self, limit: int = 20) -> list[dict[str, Any]]:
        return [p.to_dict() for p in
                sorted(self.people.values(), key=lambda p: -p.appearances)[:limit]]

    def partnerships(self, limit: int = 15) -> list[dict[str, Any]]:
        """Who seconds whom. Alliances are visible in the seconding record."""
        pairs: collections.Counter = collections.Counter()
        for m in self.motions:
            if m.moved_by and m.seconded_by:
                pairs[(m.moved_by, m.seconded_by)] += 1
        return [{"mover": a, "seconder": b, "times": n}
                for (a, b), n in pairs.most_common(limit)]

    def dissenters(self, limit: int = 15) -> list[dict[str, Any]]:
        """Who voted no, and how often. Most recorded votes are unanimous, so
        a nay is the rarest and most informative thing in the record."""
        out = [{"person": p.name, "nays": p.votes.get("nay", 0),
                "yeas": p.votes.get("yea", 0)}
               for p in self.people.values() if p.votes.get("nay")]
        out.sort(key=lambda d: -d["nays"])
        return out[:limit]

    def divided_motions(self, limit: int = 15) -> list[dict[str, Any]]:
        """The ones that were not unanimous -- where the disagreement was."""
        out = []
        for m in self.motions:
            if m.recorded and m.unanimous is False:
                nay = [v.person for v in m.votes if v.cast == "nay"]
                out.append({"text": m.text[:200], "outcome": m.outcome,
                            "against": nay, "date": m.date,
                            "page_url": m.provenance.page_url if m.provenance else ""})
        return out[:limit]

    def report(self) -> dict[str, Any]:
        recorded = [m for m in self.motions if m.recorded]
        bad = [m for m in recorded if not m.rolls_agree]
        # How many recorded votes could actually be checked. Without this,
        # "0 rolls that do not reconcile" reads as verification when most rolls
        # simply had no tally to reconcile against.
        checked = [m for m in recorded
                   if any(getattr(r, "checked", False) for r in m.rolls)]
        outcomes = collections.Counter(m.outcome for m in self.motions)
        return {
            "people": len(self.people),
            "motions": len(self.motions),
            "outcomes": dict(outcomes),
            "recorded_votes": len(recorded),
            "rolls_that_do_not_reconcile": len(bad),
            "rolls_checkable": len(checked),
            "rolls_with_no_tally": len(recorded) - len(checked),
            # Every motion, with its text, its mover and the page it is on.
            # report() returned counts only, so "81 carried" resolved to
            # nothing -- in a project whose entire claim is that every number
            # resolves to the scan it came from. Motion.to_dict already carried
            # all of it and was called by nobody.
            "motions_detail": [m.to_dict() for m in self.motions[:200]],
            "most_active": self.most_active(),
            "partnerships": self.partnerships(),
            "dissenters": self.dissenters(),
            "divided": self.divided_motions(),
            "not_measured": [
                "Whether a carried motion was ever carried out. A resolution is "
                "a promise; the outcome lives in a later document, and belongs "
                "in the frontier as a question with a known prerequisite.",
                "Identity across spelling. 'Eisenberger' and an OCR-damaged "
                "'Eisenherger' are two people here until a person says otherwise.",
                "Anything said but not moved. Debate, argument and the reasons "
                "for a vote are in the text and are not parsed.",
            ],
        }


def read_document(
    pages: Iterable[PageText],
    *,
    body: str = "",
    year: str = "",
) -> Ledger:
    """Read every page of one volume into a ledger."""
    ledger = Ledger()
    for page in pages:
        motions = read_page(page, body=body, year=year)
        ledger.add(motions, roles_from=" ".join(page.text.split()))
    return ledger
