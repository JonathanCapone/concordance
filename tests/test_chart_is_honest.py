"""The reading chart must not draw a shape nobody measured.

Series here are two to five points, spread irregularly across decades. OMEGA's
original plots by array index because a sensor reports on a cadence; this
archive does not, and plotting by index would space 1961, 1962 and 1966 evenly
and erase a four-year silence. In a project whose argument is that silence is a
finding, that is the one thing the chart must not do.
"""

from __future__ import annotations

import re

import pytest

import concordance.server as S


@pytest.fixture(scope="module")
def chart_js() -> str:
    page = S.State().html()
    m = re.search(r"function chart\(s\)\{.*?\n\}\n", page, re.S)
    assert m, "chart() missing from the rendered page"
    return m.group(0)


def test_the_x_axis_is_the_year_not_the_index(chart_js: str) -> None:
    """The whole point. If this reverts to index plotting, gaps vanish."""
    assert "p[0]" in chart_js
    assert "x0" in chart_js and "x1" in chart_js
    assert "index" not in chart_js.lower()


def test_a_multi_year_gap_is_drawn_differently(chart_js: str) -> None:
    assert "stroke-dasharray" in chart_js
    assert "xs[i]-xs[i-1])>1" in chart_js.replace(" ", "")


def test_the_legend_explains_the_dash(chart_js: str) -> None:
    assert "years with no reading" in chart_js


def test_a_single_reading_is_not_drawn_as_a_trend(chart_js: str) -> None:
    """One point is a number, not a line. It says so."""
    assert "not a trend" in chart_js
    assert "one reading" in chart_js


def test_everything_drawn_is_escaped(chart_js: str) -> None:
    """Labels and units come from model output and archive text."""
    for expr in ("esc(s.label", "esc(unit)"):
        assert expr in chart_js.replace(" ", "").replace("esc(s.label", "esc(s.label")


def test_the_chart_survives_the_real_series(chart_js: str) -> None:
    """Against the shipped data rather than a fixture."""
    state = S.State()
    # State.places holds dicts (place, raw, lat, lon, years, reported...),
    # not bare strings.
    read = [p for p in state.places if p.get("raw")][:6]
    assert read
    drawn = 0
    for entry in read:
        town = state.town(entry["place"], entry["raw"])
        for s in (town.get("series") or []):
            pts = s.get("points") or []
            assert all(len(p) >= 2 for p in pts)
            drawn += 1
    assert drawn, "no series to draw"
