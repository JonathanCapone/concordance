"""The committed static pages must not contradict the data they are built from.

These are the most double-clickable files in the repository -- a reviewer opens
`portal/index.html` before reading any code -- and they are exports, so they go
stale silently while every test still passes.

They did. The landing page published 49% extraction precision for long after the
harness bug that produced it had been found, fixed and written up; the README
exists partly to disown that number. A town page quoted 88% precision from a
sentence typed into its template, through two subsequent changes to the figure.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PORTAL = Path("portal")
REPORT = Path("data/results/gold_report.json")


def _totals() -> dict:
    return json.loads(REPORT.read_text(encoding="utf-8"))["totals"]


@pytest.mark.skipif(not (PORTAL / "index.html").exists(), reason="no built portal")
def test_the_landing_page_quotes_the_measured_precision():
    html = (PORTAL / "index.html").read_text(encoding="utf-8")
    # Match the value immediately preceding its own label, whatever markup
    # wraps it, so a change of template does not silently disable the check.
    published = re.search(
        r"(\d+)%<[^>]*>(?:<[^>]*>)*\s*extraction precision", html)
    assert published, "the landing page no longer states an extraction precision"
    assert int(published.group(1)) == round(_totals()["precision"] * 100), (
        "the committed landing page disagrees with data/results/gold_report.json "
        "-- rebuild it with scripts/build_index.py"
    )


@pytest.mark.skipif(not (PORTAL / "owen-sound.html").exists(), reason="no town page")
def test_a_town_page_does_not_quote_accuracy_from_memory():
    html = (PORTAL / "owen-sound.html").read_text(encoding="utf-8")
    totals = _totals()
    assert f"{totals['precision']:.1%}" in html, (
        "the town page's accuracy sentence is stale or hard-coded -- it is built "
        "by scripts/build_town_page.py from the gold report"
    )


@pytest.mark.skipif(not (PORTAL / "index.html").exists(), reason="no built portal")
def test_the_card_does_not_promise_more_than_the_page_behind_it():
    """The card counted every Owen Sound record and the page shows one facility.

    It advertised "Owen Sound, 1963-1992, 120 readings" against a page ending in
    1972 with 87 -- the difference being the town's drinking-water reports, which
    measure what came out of taps rather than what went into the river. A reader
    discovers that gap by clicking, which is the worst way to find it.
    """
    index = (PORTAL / "index.html").read_text(encoding="utf-8")
    card = re.search(r"Owen Sound, (\d{4})–(\d{4})</h2><p>(\d+) readings", index)
    if not card:
        pytest.skip("no Owen Sound card in this build")
    town = (PORTAL / "owen-sound.html")
    if not town.exists():
        pytest.skip("no town page to compare against")
    page = town.read_text(encoding="utf-8")
    assert card.group(1) in page and card.group(2) in page, (
        "the card's year span does not appear on the page it links to"
    )


@pytest.mark.skipif(
    not (PORTAL / "index.html").exists() or not (PORTAL / "silence.html").exists(),
    reason="no built silence pages",
)
def test_the_published_silence_claim_preserves_the_catalogue_boundary():
    pages = "\n".join(
        (PORTAL / name).read_text(encoding="utf-8")
        for name in ("index.html", "silence.html")
    ).lower()
    for overclaim in (
        "municipalities stop filing",
        "municipalities stop reporting",
        "what ontario stopped measuring",
        "the silence is real",
        "this one series died",
    ):
        assert overclaim not in pages
    assert "title-derived report series" in pages
    assert "individual gaps remain unexplained" in pages
    assert "not a collection-wide scanning stop" in pages
