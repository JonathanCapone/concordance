"""What makes two claims claims about the same thing.

Get this wrong in either direction and the dispute ledger lies. Too few fields
and unrelated readings are reported as contradicting each other; too many and a
genuine disagreement is split apart and never surfaces.

`kind` and `qualifier` were missing. The fourth time in this project that an
identity merged different things by omitting a field.
"""

from __future__ import annotations

from groundtruth.disputes import SLOT_FIELDS, slot_of


def _rec(**kw):
    base = {"place": "Brantford", "facility": "water pollution control plant",
            "parameter": "BOD", "unit": "mg/L", "period": 1966, "stream": "effluent",
            "kind": "observation", "qualifier": None}
    base.update(kw)
    return base


def test_a_limit_does_not_contest_a_measurement() -> None:
    """Brantford's effluent averaged 31.4 mg/L against its own 15 mg/L limit.
    That is not a data dispute -- it is the finding, and the single most
    interesting thing the archive says about that plant that year."""
    measured = _rec(kind="observation", value=31.4, qualifier="average")
    limit = _rec(kind="standard", value=15.0)
    assert slot_of(measured) != slot_of(limit)


def test_a_limit_does_not_contest_a_design_specification() -> None:
    """15 mg/L is what the plant was allowed to discharge; 175 is what it was
    built to handle. Both are true at once and neither reads anything."""
    limit = _rec(kind="standard", value=15.0, stream="unknown")
    design = _rec(kind="design", value=175.0, stream="unknown")
    assert slot_of(limit) != slot_of(design)


def test_a_minimum_a_maximum_and_an_average_are_three_quantities() -> None:
    """From one real sentence: "ranging from a minimum reduction in BOD of 4.5
    to a maximum of 99, averaging 91.6". Three claims were fighting over one
    slot for a sentence that plainly states three different things."""
    lo = _rec(qualifier="minimum", value=4.5)
    hi = _rec(qualifier="maximum", value=99.0)
    avg = _rec(qualifier="average", value=91.6)
    assert len({slot_of(lo), slot_of(hi), slot_of(avg)}) == 3


def test_two_readings_of_the_same_thing_still_share_a_slot() -> None:
    """The other direction. If this splits, real disagreements stop surfacing
    and the ledger becomes decorative."""
    a = _rec(value=104.0)
    b = _rec(value=26.0)
    assert slot_of(a) == slot_of(b)


def test_the_slot_carries_the_fields_that_change_what_is_claimed() -> None:
    for field in ("place", "facility", "parameter", "unit", "period", "stream",
                  "kind", "qualifier"):
        assert field in SLOT_FIELDS


def test_no_published_slot_mixes_kinds() -> None:
    """The property, over the real dataset rather than fixtures."""
    import collections
    from groundtruth.disputes import (
        load_claims, load_contributions, load_vision_records,
    )
    claims = load_claims("data/results") + load_vision_records() + load_contributions()
    if not claims:
        import pytest
        pytest.skip("no records on disk")
    by = collections.defaultdict(set)
    for c in claims:
        by[slot_of(c.record)].add(c.record.get("kind"))
    mixed = {k: v for k, v in by.items() if len(v) > 1}
    assert not mixed, f"{len(mixed)} slots mix kinds, e.g. {list(mixed)[:2]}"
