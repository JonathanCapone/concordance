"""The reader splits a dense page, and it keeps labels with their numbers.

On the Owen Sound design sheet the model returned six records out of
twenty-six and stopped -- not because it could not read "Retention: 8.6 min",
but because it had already written about six records and that is how many it
writes. Handing it the page in parts took recall on the four gold pages from
32.4% to 57.4%.

Two properties have to hold for that to be worth anything, and neither is
visible by reading the HTML as text:

  1. a page thick with numbers must come back as more than one part, and a
     page with few must come back whole -- otherwise every prose page pays
     the cost for nothing;
  2. a part must not begin with an orphaned value. A specification sheet puts
     the name on one line and the number on the next, so a split between them
     publishes "Size = 18,000 gallons" with no idea what was 18,000 gallons.

The unit rule is here for the same reason. "Size: Two 408 scfm" is read as
value 2, unit "408 scfm": the measurement lands in the wrong field and
publishes as a count of something unnamed. Units that legitimately carry a
digit weld it to a letter -- gal/ft2/day -- which is what separates them.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from scripts.build_browser_reader import CHECKS_JS

pytestmark = pytest.mark.skipif(not shutil.which("node"),
                                reason="node is not installed")

DESIGN_SHEET = "\n\n".join([
    "DESIGN DATA",
    "DESIGN FLOW",
    "3.0 mgd",
    "DESIGN POPULATION",
    "25,000",
    "BOD - Raw Sewage\n- Removal",
    "180 mg/1\n40%",
    "SEWAGE PUMPING STATION\nScreening",
    "Pumps",
    "Type: Worthington\nSize: Three 3150 gpm @ 33' tdh",
    "Grit Removal",
    "Type: Aerated",
    "Size: One 18^ X 13 X 12' (18,000 gal)\nRetention: 8.6 min",
    "Pre-aeration Tank",
    "Size: One 23' 9\" X 13 X 12'",
    "(23,400 gal)\nRetention : 11.2 min",
    "OUTFALL",
    "828' to Owen Sound",
])

PROSE = (
    "PLANT EFFICIENCY\n\n"
    "The average influent BOD and suspended solids were 104 mg/1 and 224 mg/1 "
    "respectively.\n\n"
    "The plant operated without interruption throughout the year."
)


def _run(script: str):
    """Evaluate script against the reader's own shared JavaScript."""
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(CHECKS_JS + "\n" + script)
        path = fh.name
    try:
        done = subprocess.run(["node", path], capture_output=True, text=True,
                              timeout=60)
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)
    finally:
        Path(path).unlink(missing_ok=True)


def test_a_dense_page_comes_back_in_parts() -> None:
    parts = _run("console.log(JSON.stringify(splitPage(%s)))"
                 % json.dumps(DESIGN_SHEET))
    assert len(parts) > 3, f"the design sheet stayed in {len(parts)} part(s)"


def test_a_page_with_few_numbers_stays_whole() -> None:
    parts = _run("console.log(JSON.stringify(splitPage(%s)))" % json.dumps(PROSE))
    assert parts == [PROSE], "a thin page paid for a split it did not need"


def test_no_part_orphans_a_value_from_its_label() -> None:
    """The part holding 18,000 gallons must also say what held it."""
    parts = _run("console.log(JSON.stringify(splitPage(%s)))"
                 % json.dumps(DESIGN_SHEET))
    holding = [p for p in parts if "18,000 gal" in p]
    assert holding, "the grit removal volume fell out of every part"
    assert any("Grit Removal" in p for p in holding), (
        "the volume was split away from the name of the thing it measures")


def test_every_part_carries_the_page_heading() -> None:
    """DESIGN DATA is the word that makes these design values, not readings."""
    parts = _run("console.log(JSON.stringify(splitPage(%s)))"
                 % json.dumps(DESIGN_SHEET))
    assert all(p.startswith("DESIGN DATA") for p in parts)


def test_a_part_with_no_digits_is_not_worth_a_model_call() -> None:
    text = "HEADING\n\nA paragraph with no numbers at all.\n\nAnother one."
    parts = _run("console.log(JSON.stringify(splitPage(%s)))" % json.dumps(text))
    assert parts == [text]


def test_a_measurement_is_not_a_unit() -> None:
    cases = ["408 scfm", "2000 lb/day", "31 X 14 X 8'", "' dia x 25' swd",
             "78 X 32 X 12^'"]
    got = _run("console.log(JSON.stringify(%s.map(unitIsAUnit)))"
               % json.dumps(cases))
    assert got == [False] * len(cases)


def test_real_units_survive_the_rule() -> None:
    cases = ["mg/L", "%", "min", "gpm", "cu ft", "gal/ft2 /day", "gal/ft/day",
             "lb/cu ft/mo", "m3", "schools", "million gallons", ""]
    got = _run("console.log(JSON.stringify(%s.map(unitIsAUnit)))"
               % json.dumps(cases))
    assert got == [True] * len(cases)


def test_the_same_reading_twice_is_one_reading() -> None:
    """Parts overlap, so a record can arrive twice. It is not two readings."""
    records = [
        {"kind": "design", "parameter": "grit volume", "value": 18000,
         "unit": "gal", "source_text": "Size: One 18^ X 13 X 12' (18,000 gal)"},
        {"kind": "design", "parameter": "Grit Removal Size", "value": 18000,
         "unit": "gal", "source_text": "Size: One 18^ X 13 X 12' (18,000 gal)"},
        {"kind": "design", "parameter": "grit retention", "value": 8.6,
         "unit": "min", "source_text": "Retention: 8.6 min"},
    ]
    got = _run("console.log(JSON.stringify(dedupeRecords(%s)))"
               % json.dumps(records))
    assert len(got) == 2
