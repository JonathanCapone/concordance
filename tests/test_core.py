"""Tests for the parts that silently corrupt data when they break.

Priority is given to failures that produce *plausible* wrong answers rather than
crashes -- a truncated model response that loses ten good records, a design
specification charted as a measurement, an effluent value recorded as influent.
Those are the ones that look like findings.
"""

from __future__ import annotations

import pytest

from groundtruth.extract import _normalize, _parse_json_array, _salvage_objects, _to_float
from groundtruth.models import PageText, Provenance, Record, Word
from groundtruth.router import Path, route
from groundtruth.score import norm_unit, score_page, values_match


# -- provenance -------------------------------------------------------------

def test_page_url_is_zero_indexed_deep_link():
    p = Provenance("owensoundwaterpo24477", page=11, source_text="x")
    assert p.page_url.endswith("/page/n10/mode/2up")


def test_record_without_source_text_is_unusable():
    """A claim nobody can check is not evidence, whatever else is right about it."""
    r = Record(
        kind="observation", parameter="BOD", value=104, unit="mg/L",
        confidence=0.9, provenance=Provenance("x", 1, ""),
    )
    assert not r.is_usable
    assert any("not checkable" in p for p in r.problems())


def test_identical_readings_collapse_to_one_key():
    def make(conf: float, extractor: str) -> Record:
        return Record(
            kind="observation", parameter="BOD", value=104, unit="mg/L",
            place="Owen Sound", period="1969", confidence=conf,
            provenance=Provenance("id", 11, "sentence", extractor=extractor),
        )
    # Same sentence read by two different models is one reading, not two.
    assert make(0.9, "ollama:gemma4:12b").key == make(0.4, "anthropic:claude-sonnet-5").key


# -- salvage ----------------------------------------------------------------

def test_salvage_recovers_records_from_truncated_array():
    """Generation gets cut off mid-array; losing the whole page would be worse."""
    truncated = (
        '[{"kind":"observation","value":104,"source_text":"a"},'
        '{"kind":"observation","value":224,"source_text":"b"},'
        '{"kind":"observation","value":37,"unit":"mg'
    )
    got = _parse_json_array(truncated)
    assert [o["value"] for o in got] == [104, 224]


def test_salvage_respects_braces_inside_strings():
    raw = '[{"source_text":"a } b","value":5}]'
    assert len(_salvage_objects(raw)) == 1


def test_parses_fenced_json():
    assert len(_parse_json_array('```json\n[{"value":1}]\n```')) == 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("8. 8", 8.8), ("53,549.66", 53549.66), ("$36.30", 36.30), (None, None), ("none", None)],
)
def test_to_float_handles_ocr_spacing(raw, expected):
    assert _to_float(raw) == expected


def test_normalize_makes_ocr_spacing_irrelevant():
    """The provenance check must be strict about content, forgiving about spacing."""
    assert _normalize("8. 8 million gallons") == _normalize("8.8 million  gallons")


# -- routing ----------------------------------------------------------------

def _page(text: str) -> PageText:
    return PageText(identifier="x", page=1, text=text)


def test_prose_with_units_routes_to_prose():
    text = (
        "The average influent BOD and suspended solids were 104 mg/1 and 224 mg/1\n"
        "respectively. The average effluent BOD and suspended solids were 37 mg/1\n"
        "and 36 mg/1 respectively, giving an average removal of 64% BOD and 84%\n"
        "suspended solids. A total of 1243 cu. ft. of grit was removed during the\n"
        "year, for an average of 104 cu. ft. of grit removed per million gallons.\n"
    )
    assert Path.PROSE in route(_page(text)).paths


def test_regulatory_limit_routes_to_standard():
    text = (
        "The Maximum Acceptable Concentration of nitrate in drinking water is 10 mg/L.\n"
        "Where fluoridation is practised the recommended concentration is 1.2 mg/L.\n"
        "These objectives apply to all municipal supplies in the province.\n"
    )
    assert Path.STANDARD in route(_page(text)).paths


def test_dense_numeric_page_routes_to_table():
    rows = "\n".join(f"{i} 12.4 88.1 0.03 447 91.2 6" for i in range(30))
    assert Path.TABLE in route(_page(rows)).paths


def test_narrow_columns_are_still_prose():
    """Prose set in narrow columns must not be discarded for being narrow.

    Verbatim from "Hamilton : An Adventure in Good Living" (1983), which is a
    city magazine: 149 lines of unbroken prose, median 4 words to the line, not
    one reaching the old 8-word threshold. Every page of it scored prose_ratio
    0.000 and was skipped -- including this one, which states how many schools
    the city had. Measured across 8,372 pages of 34 documents, that threshold
    was discarding 20.3 points of the corpus, worst of all in the legislative
    record: Acts of the Parliament of Canada went from 265 usable pages to 861.
    """
    text = (
        "When young Johnny and young\n"
        "Katie toddle off for their first day\n"
        "at school in Hamilton, chances\n"
        "are they'll be going just around\n"
        "the corner.\n"
        "With 75 elementary schools\n"
        "under the aegis of the Hamilton\n"
        "Board of Education, and 42\n"
        "operated by the Hamilton-\n"
        "Wentworth Roman Catholic\n"
        "Separate School Board, few\n"
        "children have far to travel.\n"
    )
    assert Path.PROSE in route(_page(text)).paths


def test_narrow_columns_do_not_turn_tables_into_prose():
    """The fix must not swallow tabular pages, which have short lines too."""
    rows = "\n".join(f"{i} 12.4 88.1 0.03 447 91.2 6" for i in range(30))
    assert Path.PROSE not in route(_page(rows)).paths


def test_wide_pages_route_exactly_as_before():
    """The adaptive threshold is clamped so full-width pages are unaffected."""
    from groundtruth.router import MAX_PROSE_WORDS, prose_line_width

    wide = ["the quick brown fox jumps over the lazy dog again and again"] * 10
    assert prose_line_width(wide) == MAX_PROSE_WORDS


def test_index_entries_are_too_short_to_be_prose():
    """A two-word-per-line index must not read as a paragraph."""
    from groundtruth.router import MIN_PROSE_WORDS, prose_line_width

    index = ["Ashcroft 44", "Barrie 91", "Cayuga 12", "Dundas 7"]
    assert prose_line_width(index) == MIN_PROSE_WORDS
    assert Path.PROSE not in route(_page("\n".join(index))).paths


def test_sparse_map_page_survives_the_length_gate():
    """A full-page map OCRs to almost nothing; skipping it would lose the map."""
    r = route(_page("Scale 1:50000  legend  contour  township  UTM"))
    assert Path.MAP in r.paths


def test_boilerplate_is_skipped():
    r = route(_page("Digitized by the Internet Archive in 2015 https://archive.org/details/x"))
    assert r.paths == [Path.SKIP]


# -- scoring ----------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "canonical"),
    [("mg/1", "mg/l"), ("per cent", "%"), ("million gallons per day", "mgd"), ("cu. ft.", "cu ft")],
)
def test_unit_aliases_normalize(raw, canonical):
    assert norm_unit(raw) == canonical


def test_values_match_absorbs_ocr_spacing_but_not_magnitude():
    assert values_match(8.8, 8.8)
    assert not values_match(8.8, 88)


def _rec(kind: str, value: float, unit: str, stream: str = "unknown") -> Record:
    return Record(
        kind=kind, parameter="BOD", value=value, unit=unit, stream=stream,
        confidence=0.9, provenance=Provenance("x", 1, "s"),
    )


GOLD = [
    {"kind": "observation", "parameter": "BOD", "value": 104, "unit": "mg/L", "stream": "influent"},
    {"kind": "design", "parameter": "BOD", "value": 180, "unit": "mg/L", "stream": "raw"},
]


def test_perfect_extraction_scores_perfectly():
    s = score_page(GOLD, [_rec("observation", 104, "mg/1", "influent"),
                          _rec("design", 180, "mg/1", "raw")], 1)
    assert (s.precision, s.recall, s.kind_accuracy, s.stream_accuracy) == (1.0, 1.0, 1.0, 1.0)


def test_design_reported_as_observation_is_caught_by_kind_accuracy():
    """The dangerous error: values all correct, but a spec charted as a measurement."""
    s = score_page(GOLD, [_rec("observation", 104, "mg/L", "influent"),
                          _rec("observation", 180, "mg/L", "raw")], 1)
    assert s.precision == 1.0 and s.recall == 1.0     # looks perfect on values
    assert s.kind_accuracy == 0.5                     # and is not
    assert s.kind_confusions()[0][:2] == ("design", "observation")


def test_hallucinated_record_lowers_precision():
    s = score_page(GOLD, [_rec("observation", 104, "mg/L", "influent"),
                          _rec("observation", 999, "mg/L")], 1)
    assert s.precision == 0.5


# -- word boxes -------------------------------------------------------------

def test_find_boxes_locates_a_phrase_for_highlighting():
    words = [Word(t, i * 10, 0, i * 10 + 8, 10)
             for i, t in enumerate("The average influent BOD was 104 mg/1".split())]
    page = PageText(identifier="x", page=1, text=" ".join(w.text for w in words), words=words)
    boxes = page.find_boxes("average influent BOD")
    assert [b.text for b in boxes] == ["average", "influent", "BOD"]


def test_a_sentence_named_facility_survives_the_document_title():
    """One document routinely covers several facilities.

    A page describing a city's hospitals gives 430 beds, 640 beds, 620 beds and
    420 beds -- four hospitals, not a contradiction -- and each sentence names
    which. Without a facility from the sentence they share one identity, and the
    dispute ledger reports the city's hospital system as a four-way
    disagreement. The document title says only "Hamilton".
    """
    from groundtruth.disputes import slot_of

    general = {"place": "Hamilton", "facility": "Hamilton General Hospital",
               "parameter": "beds", "unit": "beds", "period": "1983"}
    josephs = dict(general, facility="St. Joseph's Hospital")
    assert slot_of(general) != slot_of(josephs)

    untitled = dict(general, facility=None)
    also_untitled = dict(josephs, facility=None)
    assert slot_of(untitled) == slot_of(also_untitled)   # the failure it prevents


def test_a_month_is_not_a_town():
    """31 Brantford records landed under "January", "February", "March"...

    Reading a monthly table, the model put the row label in `place`, and the
    frontier then proposed reading "April's council minutes". The month is
    folded back into the period, where it is more precise than the year alone.
    """
    from groundtruth.extract import _period_of, _place_of

    monthly = {"place": "March", "period": "1962"}
    assert _place_of(monthly) is None
    assert _period_of(monthly) == "1962-03"


def test_a_place_that_merely_shares_a_word_with_the_calendar_stays():
    """March Township is a real place in Ontario. Only bare month names move."""
    from groundtruth.extract import _period_of, _place_of

    township = {"place": "March Township", "period": "1962"}
    assert _place_of(township) == "March Township"
    assert _period_of(township) == "1962"


def test_a_misfiled_month_with_no_year_does_not_invent_one():
    from groundtruth.extract import _period_of

    assert _period_of({"place": "April", "period": ""}) is None
    assert _period_of({"place": "April", "period": "1962-05"}) == "1962-05"


def test_whitespace_around_a_slash_is_not_a_different_unit():
    """A correct extraction was scored as both a miss and a fabrication.

    The gold set writes "gal/ft2/day"; the model returned "gal/ft2 /day" for the
    same reading. Nothing about a space beside a solidus changes what the unit
    means, and the mismatch cost the record twice -- once in recall and once in
    precision.
    """
    assert norm_unit("gal/ft2 /day") == norm_unit("gal/ft2/day")
    assert norm_unit("lb / day") == norm_unit("lb/day")


def test_normalising_units_does_not_flatten_a_real_difference():
    """The scorer must not be loosened into flattering itself.

    "pounds" and "pounds per month" are the same value with different precision,
    and treating them as equal would raise the published accuracy by pretending
    a rate was recorded when only a quantity was. That is the ruler bending to
    the thing it measures, which this project has already done once at a cost
    of most of a day.
    """
    assert norm_unit("pounds") != norm_unit("pounds per month")
    assert norm_unit("gallons") != norm_unit("gallons per month")
