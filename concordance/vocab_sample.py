"""Decide when we have seen enough of the archive's vocabulary.

The vocabulary is the part of this project that cannot be distributed. Everything
else can happen on whoever's machine wants the answer, but what a measurement
*means* has to be decided once, centrally, before anyone starts reading -- because
a record whose parameter does not resolve is extracted perfectly and then dropped
from every chart in silence. An audit of 281 records found 36.7% in exactly that
state. The extractor was not the problem. The list was.

So the plan is one central pass on rented hardware that samples the corpus wide
enough to have seen the vocabulary, and the only real question is *how wide*.
This module answers that with a number instead of a feeling.

The metric is deliberately plain: **the chance that the next reading names
something we have never seen.** That is Good-Turing's estimator, f1/N -- the
share of terms seen exactly once. If one reading in twenty still brings a new
term, we have not sampled enough. If one in five hundred does, we have.

Three things this guards against, each of which would otherwise produce a curve
that flattens beautifully and lies:

**The model names things the page did not.** Measured on 844 real readings: 32%
of parameter names do not appear anywhere in the sentence they were read from.
"The tanks are 70 feet in diameter" yields `diameter`; one sentence about a pass
being 30 feet wide, 15 deep and 200 long yields three records. That is correct
interpretation, not hallucination -- but it is a fact about the model, and
counting it as the archive's vocabulary measures the wrong thing.

The first version of this docstring said the model's naming vocabulary was
"small and saturates almost immediately", so pooling would flatten the curve
early. Running it proved that backwards. The two populations, over the same 844
readings:

    archive language   134 terms   57 seen once   miss rate 0.099
    model language     170 terms  121 seen once   miss rate 0.448

The model's vocabulary is *larger* and nowhere near saturating, because it is
describing rather than quoting and every page's phrasing suggests a fresh name.
Pooling them would therefore have made coverage look permanently worse and never
converge -- the opposite failure from the one predicted, arriving at the same
place. The separation stands; the reasoning behind it was wrong and is corrected
here rather than quietly fixed. See `Term.archive_language`.

**A pooled figure hides an unsampled corner.** Coverage across the whole corpus
can read 97% while an entire agency's vocabulary is untouched, because that
agency is 0.4% of the documents. The rule is therefore a *minimum across strata*,
never a total. A stratum with too few readings to judge is reported as unjudged
rather than quietly counted as covered.

**OCR damage manufactures singletons.** f1 is the numerator of the whole metric,
and a scanner that turns "ammonium" into "aitunonium" inflates it. Inspection of
the real singleton tail found roughly one term in eight damaged that way -- less
than feared, because most singletons are real terms nobody had listed yet
(`hydraulic loading`, `contact period`, `phenolics`). Damaged terms are not
dropped: dropping them silently is how a measurement starts lying. Both figures
are reported, and if they disagree the report says so.

Nothing here decides what a term *means*. That stays with a person, in
`vocab_builder`, for the reason that module explains at length.
"""

from __future__ import annotations

import collections
import json
import math
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from .parameters import resolve as resolve_parameter
from .vocab_builder import _stem

#: Collections that say which library scanned an item rather than what it is
#: about. Every item in the corpus carries several of these, so they cannot
#: serve as strata -- `governmentpublications` alone would be one stratum of
#: 104,241.
GENERIC_COLLECTIONS = frozenset({
    "toronto", "governmentpublications", "robarts", "university_of_toronto",
    "additional_collections", "americana", "inlibrary", "printdisabled",
    "internetarchivebooks", "microfiche", "fav-swswswswsw", "fedlink",
})

#: Below this many readings a stratum's coverage is not estimated. Good-Turing
#: on a handful of observations reports whatever the first few terms happened to
#: be; the honest output is "not enough to say", not a confident number.
MIN_READINGS_TO_JUDGE = 40

#: Target for the stopping rule: fewer than one reading in forty brings a term
#: we have never seen. Set from the real tail rather than taste -- 22 documents
#: of a single domain reached 0.672 coverage (one reading in three was new), so
#: 0.975 is roughly an order of magnitude past where the current data sits and
#: still cheap at sampling prices.
TARGET_COVERAGE = 0.975

#: A document's later pages repeat its earlier vocabulary. Measured across ten
#: extracted documents, the first half of the pages carried 30-80% of the whole
#: document's distinct terms (median near half) -- so reading all 3,164 pages of
#: the largest item buys far less than 40 pages each from 79 different ones.
#: The largest 10,000 documents hold 44% of the corpus's 22.1M pages, so without
#: a cap a page-uniform sample is mostly a survey of long documents.
DEFAULT_PAGE_CAP = 40


# --------------------------------------------------------------------------
# what we saw
# --------------------------------------------------------------------------

#: Units that can only ever express a bulk quantity, never a concentration.
#: Used to catch the case where `resolve()` names a measure the record's own
#: unit contradicts -- see `contradicted()`.
_BULK = re.compile(
    r"\b(lbs?|pounds?|tons?|tonnes?|kg|kilograms?|grams?|"
    r"gal|gallons?|litres?|liters?|m3|cubic\s*(feet|foot|metres?|meters?)|"
    r"acre[- ]?feet)\b", re.I)

#: Units that can only be a rate.
_PER_TIME = re.compile(r"(/\s*(d|day|hr|hour|min|sec|yr|year)|per\s+(day|hour|minute|year|"
                       r"capita)|mgd|cfs)\b", re.I)


def contradicted(measure: str, unit: str | None) -> bool:
    """Does the resolved measure disagree with the unit the record carries?

    `resolve()` picks a substance by substring and then guesses the measure,
    falling through to `concentration` when nothing else fits. So a BOD figure
    of 3,639,400 **pounds** and a BOD figure of 30 **mg/L** land under the same
    identity, and an annual loading joins a series of effluent readings.
    Measured on the records currently on disk: 39 of 698, 5.6%.

    This matters to the stopping rule more than it looks. If coverage counts
    only records that fail to resolve, the rule is a ratchet: accept enough
    vocabulary proposals and any target is met, whether or not a single mapping
    is right. Counting a contradicted resolution as a miss is what stops the
    number being buyable.
    """
    if not unit:
        return False
    u = str(unit)
    if measure == "concentration":
        return bool(_BULK.search(u)) and "/" not in u.replace("mg/", "").replace("ug/", "")
    if measure == "total":
        return bool(_PER_TIME.search(u))
    return False


@dataclass
class Term:
    """One measured identity, and whether the archive or the model named it.

    Keyed on stem AND measure, not stem alone. `_stem` strips exactly the words
    `resolve()` reads the measure from -- "average", "total", "rate" -- so nine
    of the 155 stems in the current data span more than one canonical identity.
    The stem "flow" covers a rate, a removal and a total; "BOD" covers a
    concentration and a total. Counting those as one term understates the
    vocabulary and merges series that must never be plotted together, which is
    the exact defect that put removal percentages on a concentration axis.
    """

    stem: str
    measure: str = ""
    count: int = 0
    verbatim: int = 0          # times the name appeared in its own source sentence
    strata: set[str] = field(default_factory=set)
    units: collections.Counter = field(default_factory=collections.Counter)
    variants: collections.Counter = field(default_factory=collections.Counter)
    resolved: bool = False
    contested: int = 0         # resolved to a measure its own unit denies
    clean_pages: int = 0       # sightings on pages with decent OCR
    damaged_pages: int = 0     # sightings only on badly scanned pages
    families: set[str] = field(default_factory=set)
    example: str = ""

    @property
    def key(self) -> str:
        return f"{self.stem}|{self.measure}" if self.measure else self.stem

    @property
    def settled(self) -> bool:
        """Resolves, and nothing about the record argues with the answer.

        An unresolved term is a known gap. A *contested* one is worse: it is a
        gap wearing the costume of an answer, and it is invisible to any count
        of what failed to resolve.
        """
        return self.resolved and self.contested == 0

    @property
    def archive_language(self) -> bool:
        """The page said this, in these words, at least once.

        The distinction the whole stopping rule rests on. A term the model
        supplied is a fact about the model.
        """
        return self.verbatim > 0

    @property
    def suspect(self) -> bool:
        """Only ever seen on pages the scanner made a mess of."""
        return self.damaged_pages > 0 and self.clean_pages == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "term": self.stem,
            "measure": self.measure,
            "count": self.count,
            "archive_language": self.archive_language,
            "verbatim_sightings": self.verbatim,
            "strata": sorted(self.strata),
            "families": len(self.families),
            "units": self.units.most_common(4),
            "written_as": [v for v, _ in self.variants.most_common(5)],
            "already_resolves": self.resolved,
            "contested": self.contested,
            "settled": self.settled,
            "suspect_ocr": self.suspect,
            "example": self.example[:160],
        }


@dataclass
class Reading:
    """One extracted record, reduced to what the vocabulary question needs."""

    parameter: str
    unit: str | None
    source_text: str
    stratum: str
    identifier: str = ""
    #: The title family, not the item. 44.4% of the corpus shares a title
    #: family with another item -- "annual report" alone covers 992 of them --
    #: so Brantford 1962 and Brantford 1963 are two identifiers and one
    #: vocabulary. Counting families rather than documents is what stops a
    #: stratum looking well sampled because one report was read twelve times.
    family: str = ""
    page: int | None = None
    ocr_confidence: float | None = None


# --------------------------------------------------------------------------
# the estimators
# --------------------------------------------------------------------------

@dataclass
class Coverage:
    """Good-Turing coverage and Chao1 richness for one population of terms."""

    readings: int
    observed: int
    singletons: int
    doubletons: int

    @property
    def miss_rate(self) -> float:
        """Chance the next reading names something never seen before.

        Good-Turing: the singletons ARE the estimate. A term seen once is the
        evidence that terms seen zero times exist.
        """
        if self.readings <= 0:
            return 1.0
        return self.singletons / self.readings

    @property
    def coverage(self) -> float:
        return 1.0 - self.miss_rate

    @property
    def judged(self) -> bool:
        return self.readings >= MIN_READINGS_TO_JUDGE

    @property
    def chao1(self) -> float:
        """Lower bound on how many distinct terms actually exist.

        Uses the bias-corrected form, which stays finite when nothing has been
        seen exactly twice -- the uncorrected f1^2/(2*f2) divides by zero there,
        and early in a run f2 is routinely zero.
        """
        f1, f2 = self.singletons, self.doubletons
        return self.observed + (f1 * (f1 - 1)) / (2 * (f2 + 1))

    @property
    def chao1_ci95(self) -> tuple[float, float]:
        """Log-normal confidence interval on the richness estimate.

        Asymmetric on purpose: the estimate is a lower bound, so the interval it
        deserves is not symmetric around it.
        """
        s_obs, est = self.observed, self.chao1
        extra = est - s_obs
        if extra <= 0 or s_obs <= 0:
            return (float(s_obs), float(s_obs))
        f1, f2 = self.singletons, self.doubletons
        r = f1 / (f2 + 1)
        var = (f2 + 1) * (0.5 * r ** 2 + r ** 3 + 0.25 * r ** 4)
        if var <= 0:
            return (float(s_obs), est)
        c = math.exp(1.96 * math.sqrt(math.log(1.0 + var / (extra ** 2))))
        return (s_obs + extra / c, s_obs + extra * c)

    def to_dict(self) -> dict[str, Any]:
        lo, hi = self.chao1_ci95
        return {
            "readings": self.readings,
            "terms_seen": self.observed,
            "seen_once": self.singletons,
            "seen_twice": self.doubletons,
            "miss_rate": round(self.miss_rate, 5),
            "coverage": round(self.coverage, 5),
            "judged": self.judged,
            "terms_estimated_to_exist": round(self.chao1, 1),
            "estimate_ci95": [round(lo, 1), round(hi, 1)],
        }


def _coverage_of(terms: Iterable[Term]) -> Coverage:
    terms = list(terms)
    counts = [t.count for t in terms]
    return Coverage(
        readings=sum(counts),
        observed=len(terms),
        singletons=sum(1 for c in counts if c == 1),
        doubletons=sum(1 for c in counts if c == 2),
    )


# --------------------------------------------------------------------------
# the survey
# --------------------------------------------------------------------------

@dataclass
class Survey:
    """Everything seen so far, and what it implies about what has not been."""

    terms: dict[str, Term] = field(default_factory=dict)
    readings: int = 0
    pages: int = 0
    documents: set[str] = field(default_factory=set)
    strata_planned: dict[str, int] = field(default_factory=dict)
    strata_read: collections.Counter = field(default_factory=collections.Counter)
    #: New archive-language terms per round, in order. The discovery curve.
    curve: list[int] = field(default_factory=list)
    #: Readings per round, so the curve can be plotted against effort rather
    #: than against round number -- rounds are not the same size.
    curve_readings: list[int] = field(default_factory=list)

    # -- populations ------------------------------------------------------

    def archive_terms(self) -> list[Term]:
        """What the documents call things, in their own words."""
        return [t for t in self.terms.values() if t.archive_language]

    def model_terms(self) -> list[Term]:
        """What the model called things when the page did not name them."""
        return [t for t in self.terms.values() if not t.archive_language]

    def unsettled_terms(self) -> list[Term]:
        """Archive language the vocabulary cannot place, or places wrongly.

        Both count as work. A term that does not resolve is a visible gap; a
        term that resolves to a measure its own unit denies is the same gap
        wearing the costume of an answer, and only this list sees it.
        """
        return [t for t in self.archive_terms() if not t.settled]

    # -- coverage ---------------------------------------------------------

    def coverage(self, *, archive_only: bool = True) -> Coverage:
        return _coverage_of(self.archive_terms() if archive_only else self.terms.values())

    def coverage_excluding_suspect(self) -> Coverage:
        """The same figure with OCR-damaged terms removed.

        Reported alongside the real one rather than instead of it. If these two
        disagree materially the sample is being driven by scan damage, and that
        is a finding about the sample, not a number to quietly prefer.
        """
        return _coverage_of(t for t in self.archive_terms() if not t.suspect)

    def coverage_by_stratum(self) -> dict[str, Coverage]:
        by: dict[str, list[Term]] = collections.defaultdict(list)
        for t in self.archive_terms():
            for s in t.strata:
                # A term's count is not divisible across strata without keeping
                # per-stratum counts, so each stratum sees the term with the
                # weight it actually contributed.
                by[s].append(t)
        return {s: _coverage_of(ts) for s, ts in by.items()}

    # -- the stopping rule ------------------------------------------------

    def done(self, *, target: float = TARGET_COVERAGE) -> bool:
        """Every planned stratum has been judged, and every one has passed.

        A total can read 97% while an entire agency is untouched, because that
        agency is a rounding error in document count and the vocabulary we are
        missing is exactly the vocabulary of the corners. So the rule is a
        minimum across strata, never a pooled figure.

        And a stratum nobody sampled cannot pass. An earlier version took the
        minimum over *judgeable* strata only, which quietly excused every corner
        too small to have been reached -- so the run would stop with an agency
        entirely unread and a coverage figure of 0.98 to show for it. Being
        unjudged is a reason to keep going, not an exemption.
        """
        by_stratum = self.coverage_by_stratum()
        if not by_stratum:
            return False
        if self.unjudged_strata():
            return False
        return min(c.coverage for c in by_stratum.values()) >= target

    def weakest_strata(self, limit: int = 10) -> list[dict[str, Any]]:
        """Where the next sampling round should go, worst first."""
        out = []
        for s, c in self.coverage_by_stratum().items():
            out.append({
                "stratum": s, "readings": c.readings, "terms": c.observed,
                "coverage": round(c.coverage, 4), "judged": c.judged,
                "still_missing_est": max(0, round(c.chao1 - c.observed, 1)),
            })
        out.sort(key=lambda d: (d["judged"], d["coverage"]))
        return out[:limit]

    def unjudged_strata(self) -> list[str]:
        """Planned but never sampled enough to say anything about.

        Named explicitly because a stratum with no data is the single most
        likely place for the whole estimate to be wrong, and it is invisible in
        any pooled figure.
        """
        cov = self.coverage_by_stratum()
        return sorted(s for s in self.strata_planned
                      if s not in cov or not cov[s].judged)

    # -- ingest -----------------------------------------------------------

    def observe(self, readings: Sequence[Reading], *, ocr_floor: float = 60.0) -> int:
        """Fold a round of readings in. Returns new archive-language terms.

        `ocr_floor` is on Internet Archive's own per-page confidence, where
        higher is better -- verified on this corpus rather than assumed, because
        the obvious reading of that field is backwards. Clean pages score around
        77; the floor sits below that so only genuinely poor scans are flagged.
        """
        before = {t.key for t in self.archive_terms()}

        for r in readings:
            raw = str(r.parameter or "").strip()
            if not raw:
                continue
            stem = _stem(raw)
            if not stem:
                continue
            parameter = resolve_parameter(raw, r.unit)
            measure = parameter.measure if parameter else ""
            key = f"{stem}|{measure}" if measure else stem
            term = self.terms.get(key)
            if term is None:
                term = self.terms[key] = Term(stem=stem, measure=measure)
            term.count += 1
            term.strata.add(r.stratum)
            term.variants[raw] += 1
            if r.family:
                term.families.add(r.family)
            if r.unit:
                term.units[str(r.unit)] += 1
            if parameter is not None:
                term.resolved = True
                if contradicted(parameter.measure, r.unit):
                    term.contested += 1
            if r.ocr_confidence is None or r.ocr_confidence >= ocr_floor:
                term.clean_pages += 1
            else:
                term.damaged_pages += 1
            # The circularity control. Compared on the raw name, not the stem,
            # because the stem strips exactly the words ("average", "total",
            # "concentration") whose presence or absence is the evidence.
            if raw.lower() in str(r.source_text or "").lower():
                term.verbatim += 1
                if not term.example:
                    term.example = str(r.source_text or "")
            self.readings += 1
            self.strata_read[r.stratum] += 1

        after = {t.key for t in self.archive_terms()}
        fresh = len(after - before)
        self.curve.append(fresh)
        self.curve_readings.append(len(readings))
        return fresh

    # -- output -----------------------------------------------------------

    def report(self, *, target: float = TARGET_COVERAGE) -> dict[str, Any]:
        archive = self.coverage(archive_only=True)
        model = _coverage_of(self.model_terms())
        clean = self.coverage_excluding_suspect()
        unsettled = _coverage_of(self.unsettled_terms())

        drift = abs(clean.coverage - archive.coverage)
        return {
            "effort": {
                "readings": self.readings,
                "pages": self.pages,
                "documents": len(self.documents),
                "strata_planned": len(self.strata_planned),
                "strata_reached": len(self.strata_read),
            },
            "archive_language": archive.to_dict(),
            "model_language": model.to_dict(),
            "archive_language_excluding_damaged_ocr": clean.to_dict(),
            "unsettled_only": unsettled.to_dict(),
            "contested_terms": sum(1 for t in self.archive_terms() if t.contested),
            "stopping_rule": {
                "rule": "min coverage across judgeable strata >= target",
                "target": target,
                "met": self.done(target=target),
                "weakest": self.weakest_strata(5),
                "unjudged_strata": self.unjudged_strata()[:40],
                "n_unjudged": len(self.unjudged_strata()),
            },
            "discovery_curve": {
                "new_terms_per_round": self.curve,
                "readings_per_round": self.curve_readings,
            },
            "controls": {
                "model_named_share": round(
                    model.readings / max(1, archive.readings + model.readings), 4),
                "ocr_damage_shifts_coverage_by": round(drift, 4),
                "ocr_damage_material": drift > 0.01,
            },
            "not_measured": NOT_MEASURED,
            "terms": [t.to_dict() for t in
                      sorted(self.terms.values(), key=lambda t: -t.count)],
        }


#: Stated in the output because a coverage figure invites being read as a
#: guarantee, and these are the things it is not.
NOT_MEASURED = [
    "Vocabulary on TABLE pages. Only prose pages are read here, and 9.6% of the "
    "corpus is tabular with its own vocabulary living in column headers.",
    "Whether a term MEANS what the vocabulary will say it means. This counts "
    "names; a person still decides identities in vocab_builder.",
    "Terms the extractor never emitted because its prompt did not invite them. "
    "Coverage is of what this pipeline can see, not of the documents.",
    "Anything in strata reported as unjudged -- those have no estimate at all.",
]


# --------------------------------------------------------------------------
# choosing what to read
# --------------------------------------------------------------------------

def stratum_of(item: dict[str, Any]) -> str:
    """Which corner of the archive an item belongs to.

    `collection` rather than subject or publisher because it is the only field
    populated for every item: subject is present on 42.6%, publisher on 55.7%,
    year on 67.5%. Stratifying on a field missing for a third of the corpus
    means either excluding that third or lumping it into one enormous
    "unknown" -- and the items with poor metadata are not a random third.

    The most specific collection wins, since collections nest: an item in both
    `uoftgovpubs` and `canadianagriculturallibrary` is better described by the
    smaller one. Specificity is decided by the caller's ordering.
    """
    cols = item.get("collection") or []
    cols = cols if isinstance(cols, list) else [cols]
    named = [str(c) for c in cols if str(c) not in GENERIC_COLLECTIONS]
    return named[0] if named else "unsorted"


def stratify(index: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group the whole index, putting each item in its rarest collection.

    Two passes: count how big every collection is, then assign each item to the
    smallest one it belongs to. Without this an item lands in whichever
    collection the metadata happened to list first, which put 51,137 items in
    one bucket and left `sessionalpaperscanada` with three.
    """
    items = list(index)
    size: collections.Counter = collections.Counter()
    for it in items:
        cols = it.get("collection") or []
        cols = cols if isinstance(cols, list) else [cols]
        for c in cols:
            if str(c) not in GENERIC_COLLECTIONS:
                size[str(c)] += 1

    out: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for it in items:
        cols = it.get("collection") or []
        cols = cols if isinstance(cols, list) else [cols]
        named = [str(c) for c in cols if str(c) not in GENERIC_COLLECTIONS]
        key = min(named, key=lambda c: (size[c], c)) if named else "unsorted"
        out[key].append(it)
    return dict(out)


def allocate(sizes: dict[str, int], budget: int, *, floor: int = 1) -> dict[str, int]:
    """Split a page budget across strata by the square root of their size.

    Proportional allocation would give U of T's holdings roughly half of every
    run and never reach forestry or mining, which is precisely the vocabulary
    currently missing. Equal allocation would give a three-item collection the
    same budget as 51,137 items. Square-root allocation is the standard
    compromise for exactly this shape, and it turns a 511:1 ratio into 22:1.

    `floor` guarantees no stratum is silently zero -- an unsampled stratum must
    show up as unjudged in the report, not vanish.
    """
    live = {s: n for s, n in sizes.items() if n > 0}
    if not live or budget <= 0:
        return {}
    if budget < len(live) * floor:
        # Not enough budget to floor everything: give the floor to the largest
        # strata we can afford and say nothing about the rest, rather than
        # spreading it so thin that no stratum is judgeable.
        order = sorted(live, key=lambda s: (-live[s], s))
        return {s: floor for s in order[: budget // max(1, floor)]}

    roots = {s: math.sqrt(n) for s, n in live.items()}
    total = sum(roots.values())
    out = {s: max(floor, int(budget * r / total)) for s, r in roots.items()}

    # Integer rounding overshoots; trim from the biggest allocations, never
    # below the floor, so the trimming cannot silently empty a small stratum.
    over = sum(out.values()) - budget
    while over > 0:
        s = max(out, key=lambda k: (out[k], k))
        if out[s] <= floor:
            break
        out[s] -= 1
        over -= 1
    return out


@dataclass
class Pick:
    """One document to read, and how many of its pages to spend."""

    identifier: str
    stratum: str
    pages: int
    title: str = ""
    year: str = ""


@dataclass
class Plan:
    picks: list[Pick] = field(default_factory=list)
    per_stratum: dict[str, int] = field(default_factory=dict)
    budget: int = 0
    seed: int = 0

    @property
    def pages(self) -> int:
        return sum(p.pages for p in self.picks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget_pages": self.budget, "planned_pages": self.pages,
            "documents": len(self.picks), "strata": len(self.per_stratum),
            "seed": self.seed,
            "per_stratum": dict(sorted(self.per_stratum.items(),
                                       key=lambda kv: -kv[1])),
        }


def plan(
    index: Iterable[dict[str, Any]],
    *,
    budget: int,
    seed: int = 0,
    page_cap: int = DEFAULT_PAGE_CAP,
    floor: int = 1,
) -> Plan:
    """Choose which documents to read and how much of each.

    Deterministic given a seed, because a sampling run that cannot be repeated
    cannot be checked -- and this one is meant to be paid for once and defended
    afterwards.
    """
    strata = stratify(index)
    sizes = {s: len(v) for s, v in strata.items()}
    per = allocate(sizes, budget, floor=floor)

    rng = random.Random(seed)
    picks: list[Pick] = []
    for stratum, pages_here in sorted(per.items()):
        items = strata[stratum]
        # Spread across as many DIFFERENT documents as the cap allows. A
        # document's later pages mostly repeat its earlier vocabulary, so
        # breadth beats depth per page spent.
        want_docs = max(1, math.ceil(pages_here / page_cap))
        chosen = rng.sample(items, min(want_docs, len(items)))
        left = pages_here
        for i, it in enumerate(chosen):
            share = math.ceil(left / (len(chosen) - i))
            take = min(share, page_cap, left)
            if take <= 0:
                continue
            picks.append(Pick(
                identifier=str(it.get("identifier") or ""),
                stratum=stratum, pages=take,
                title=str(it.get("title") or ""), year=str(it.get("year") or ""),
            ))
            left -= take
    return Plan(picks=picks, per_stratum=per, budget=budget, seed=seed)


# --------------------------------------------------------------------------
# persistence
# --------------------------------------------------------------------------

def write_report(survey: Survey, path: str | Path, **kwargs: Any) -> dict[str, Any]:
    payload = survey.report(**kwargs)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def readings_from_records(
    records: Iterable[dict[str, Any]],
    *,
    stratum: str = "unsorted",
    ocr_confidence: float | None = None,
) -> list[Reading]:
    """Adapt extractor output into the shape the survey wants.

    Kept separate so the survey never depends on the extractor: the same code
    runs against a local Ollama run, a rented-GPU run, and a fixture in a test.
    """
    out = []
    for r in records:
        prov = r.get("provenance") or {}
        out.append(Reading(
            parameter=str(r.get("parameter") or ""),
            unit=r.get("unit"),
            source_text=str(prov.get("source_text") or ""),
            stratum=stratum,
            identifier=str(prov.get("identifier") or ""),
            page=prov.get("page"),
            ocr_confidence=ocr_confidence,
        ))
    return out
