"""The archive's own words for what it measured.

A stratified sample across 25 collections measured the problem this solves.
Outside the water reports, **76% of readings used a parameter name the model
invented** rather than one the archive uses -- names like "cost estimate for one
boiler at keith station" and "width of strongly sheared rock". Those are not
measurement types. They are descriptions of a single sentence, they can never
recur, and a vocabulary made of them cannot saturate: 807 of 911 such names were
seen exactly once.

Meanwhile the archive's own terms recur across documents and decades --
`population`, `temperature`, `mileage`, `incubation period`, `ascorbic acid` --
and the estimator puts the number of them at about 727 (95% CI 557-987). That is
small enough to enumerate and check by hand, which is the whole reason this file
exists.

So the order is inverted. The extractor used to invent a name and
`parameters.resolve` tried to map it back afterwards, which works for water
because that table was hand-built for water and collapses everywhere else. Now
the vocabulary comes first and the model CHOOSES from it, flagging anything that
does not fit -- and those flags are how genuinely new terms get discovered
instead of drowning in paraphrase.

**Nothing here decides what a term means.** The machine proposed these entries by
clustering strings that really occur in the corpus; a person confirms them.
Deciding that "BOD removal" and "BOD exceedance frequency" are different
measurements -- one an efficiency, one a count of failures, both percentages --
is judgement, and this project has already been wrong about exactly that once.
`reviewed` on each entry records whether a human has looked at it yet, and it is
false until somebody says otherwise.
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "vocabulary" / "vocabulary.json"

def normalise(name: str) -> str:
    """The form two spellings of one term have in common.

    This is deliberately *orthographic* only: case, punctuation, Unicode width,
    HTML entities and whitespace do not make two names different. Words and
    digits always do. In particular, ``design``, ``total``, ``minimum``,
    ``maximum``, ``per capita`` and periods such as ``24 hour`` are preserved.

    Those words can change what a number means. The earlier matcher stripped
    them, which put ``population`` and ``design population`` under one key and
    collapsed rate, total, capacity and extrema variants of ``flow``. A matching
    key must never make that semantic decision. A reviewed alias can still join
    genuinely equivalent archive spellings explicitly.
    """
    text = unicodedata.normalize("NFKC", html.unescape(str(name or ""))).casefold()
    # ``isalnum`` keeps accented French letters and digits while treating every
    # punctuation mark consistently. Hyphenated and spaced spellings therefore
    # match, but no word is silently removed.
    text = "".join(ch if ch.isalnum() else " " for ch in text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class Term:
    """One measurement type, in the archive's words."""

    canonical: str
    substance: str
    measure: str
    domain: str = ""
    aliases: tuple[str, ...] = ()
    typical_units: tuple[str, ...] = ()
    readings_covered: int = 0
    #: Has a person confirmed this entry? False means the machine proposed it and
    #: nobody has checked. Published output should be able to say which.
    reviewed: bool = False

    @property
    def keys(self) -> set[str]:
        return ({normalise(self.canonical)} |
                {normalise(a) for a in self.aliases}) - {""}

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical": self.canonical, "substance": self.substance,
            "measure": self.measure, "domain": self.domain,
            "aliases": list(self.aliases), "typical_units": list(self.typical_units),
            "readings_covered": self.readings_covered, "reviewed": self.reviewed,
        }


@dataclass
class Vocabulary:
    terms: list[Term] = field(default_factory=list)
    _by_key: dict[str, Term] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._by_key = {}
        for term in self.terms:
            for k in term.keys:
                # First writer wins, so a collision is visible rather than
                # silently resolved by ordering. The reconcile pass is supposed
                # to remove these; `collisions()` reports any that survive.
                self._by_key.setdefault(k, term)

    def __len__(self) -> int:
        return len(self.terms)

    def match(self, name: str) -> Term | None:
        """The vocabulary entry a raw parameter name belongs to, if any."""
        return self._by_key.get(normalise(name))

    def is_known(self, name: str) -> bool:
        return self.match(name) is not None

    def collisions(self) -> list[tuple[str, list[str]]]:
        """Keys claimed by more than one entry. Should be empty."""
        seen: dict[str, list[str]] = {}
        for term in self.terms:
            for k in term.keys:
                seen.setdefault(k, []).append(term.canonical)
        return [(k, names) for k, names in seen.items() if len(names) > 1]

    def unreviewed(self) -> list[Term]:
        return [t for t in self.terms if not t.reviewed]

    def validation_errors(self) -> list[str]:
        """Structural defects that make matching or prompting unsafe.

        Meaning is intentionally outside this check -- that is what ``reviewed``
        records. These checks cover invariants a machine can establish without
        pretending to know meaning: usable names, paired identity fields,
        non-negative evidence counts and one owner for every matching key.
        """
        errors: list[str] = []
        for i, term in enumerate(self.terms):
            where = f"term {i + 1} ({term.canonical!r})"
            if not term.canonical.strip():
                errors.append(f"{where}: empty canonical name")
            elif not normalise(term.canonical):
                errors.append(f"{where}: canonical name has no letters or digits")
            if bool(term.substance.strip()) != bool(term.measure.strip()):
                errors.append(f"{where}: substance and measure must both be set or both be empty")
            if (isinstance(term.readings_covered, bool) or
                    not isinstance(term.readings_covered, int)):
                errors.append(f"{where}: readings_covered must be an integer")
            elif term.readings_covered < 0:
                errors.append(f"{where}: readings_covered must be non-negative")
            if not isinstance(term.reviewed, bool):
                errors.append(f"{where}: reviewed must be true or false")
            if any(not str(alias).strip() for alias in term.aliases):
                errors.append(f"{where}: aliases cannot be empty")
            if len(term.aliases) != len(set(term.aliases)):
                errors.append(f"{where}: aliases must be unique")
            if any(not str(unit).strip() for unit in term.typical_units):
                errors.append(f"{where}: typical_units cannot be empty")
            if len(term.typical_units) != len(set(term.typical_units)):
                errors.append(f"{where}: typical_units must be unique")

        for key, names in self.collisions():
            errors.append(f"matching key {key!r} is claimed by: {', '.join(names)}")
        return errors

    def require_valid(self) -> None:
        errors = self.validation_errors()
        if errors:
            raise ValueError("invalid vocabulary:\n- " + "\n- ".join(errors))

    def for_prompt(self, *, hint: str = "", limit: int = 240) -> str:
        """The list to hand a model, shortened to what will plausibly be needed.

        The whole vocabulary is a few thousand tokens, which is affordable but
        wasteful on a page about schools. Complete archive phrases visible in
        the page come first, then weaker word overlap, then the most-used terms
        overall. Phrase presence is orthographic evidence, not a semantic guess.

        Truncation is a real risk here -- a term left out is a term the model
        will invent instead -- so the caller is told to flag anything that does
        not fit rather than forced to choose badly.
        """
        h = normalise(hint)
        words = {w for w in h.split() if len(w) > 3}

        def relevance(t: Term) -> tuple[int, int, int]:
            keys = t.keys
            phrase_hit = any(f" {key} " in f" {h} " for key in keys)
            term_words = {word for key in keys for word in key.split() if len(word) > 3}
            word_hit = bool(words & term_words)
            return (-int(phrase_hit), -int(word_hit), -t.readings_covered)

        chosen = sorted(self.terms, key=relevance)[:limit]
        chosen.sort(key=lambda t: (t.domain, t.canonical))

        lines, domain = [], None
        for t in chosen:
            if t.domain != domain:
                domain = t.domain
                lines.append(f"# {domain or 'general'}")
            units = f"  [{', '.join(t.typical_units[:3])}]" if t.typical_units else ""
            lines.append(f"{t.canonical}{units}")
        return "\n".join(lines)


def _term(d: dict[str, Any]) -> Term:
    return Term(
        canonical=str(d.get("canonical") or "").strip().lower(),
        substance=str(d.get("substance") or "").strip().lower(),
        measure=str(d.get("measure") or "").strip().lower(),
        domain=str(d.get("domain") or "").strip().lower(),
        aliases=tuple(str(a).strip().lower() for a in (d.get("aliases") or []) if a),
        typical_units=tuple(str(u).strip() for u in (d.get("typical_units") or []) if u),
        readings_covered=int(d.get("readings_covered") or 0),
        reviewed=bool(d.get("reviewed", False)),
    )


@lru_cache(maxsize=4)
def load(path: str | Path = DEFAULT_PATH) -> Vocabulary:
    """The vocabulary, or an empty one if it has not been built yet.

    An empty vocabulary is not an error and must not be: the extractor falls
    back to naming things freely, which is what it did before this existed, and
    a project that refused to run without a curated file would be unusable by
    anyone who cloned it.
    """
    p = Path(path)
    if not p.exists():
        return Vocabulary(terms=[])
    payload = json.loads(p.read_text(encoding="utf-8"))
    rows: Iterable[dict[str, Any]] = (
        payload.get("terms") if isinstance(payload, dict) else payload) or []
    return Vocabulary(terms=[_term(r) for r in rows if r.get("canonical")])


def save(vocab: Vocabulary, path: str | Path = DEFAULT_PATH, *, note: str = "") -> Path:
    vocab.require_valid()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "version": 1,
        "note": note or ("Measurement types in the archive's own words. Proposed by "
                         "clustering strings that really occur in the corpus; "
                         "`reviewed` records whether a person has confirmed the entry."),
        "n_terms": len(vocab.terms),
        "terms": [t.to_dict() for t in sorted(vocab.terms,
                                              key=lambda t: (-t.readings_covered, t.canonical))],
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    load.cache_clear()
    return p
