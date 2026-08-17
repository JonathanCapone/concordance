"""The navigation is the project's loop, not a map of its modules.

Two complaints shaped this, a year apart. First: "I didn't really understand
what the tabs were for or how I would actually use any of the information" --
the nine tabs were the modules in build order. Renaming them into questions
fixed the words but not the structure, which drew the second complaint: "it
feels like not a lot of thought went into the layout of the menu and how it
all works together." Two entries answered the same question two ways, one
errored for every visitor of the shared site, and the reading queue sat four
slots from the reader it serves.

The menu is now the loop the site is: find a place, read a town, what it
found, can I trust it. These tests pin the structure and, just as much, that
consolidating it deleted nothing.
"""

from __future__ import annotations

import pytest

import concordance.server as S
from concordance.chrome import MENU


@pytest.fixture(scope="module")
def page() -> str:
    return S.State().html()


def test_the_menu_is_the_loop() -> None:
    """Four entries, in the order a visitor's involvement deepens."""
    assert [key for key, _label, _icon in MENU] == [
        "observe", "browser", "findings", "verify"]


def test_no_label_is_just_its_view_key() -> None:
    """A label is chosen for the reader, never inherited from the code."""
    for key, label, _icon in MENU:
        assert label.lower() != key.lower(), (
            f"{label!r} is just the view key {key!r}")


def test_no_tab_is_named_after_a_module() -> None:
    stale = {"observe", "record", "silence", "rivers", "verify",
             "frontier", "decisions", "disputed"}
    labels = {label.lower() for _key, label, _icon in MENU}
    assert not (labels & stale), f"module names still in the nav: {labels & stale}"


def test_rivers_is_not_a_top_level_idea() -> None:
    """It was a tab because watershed.py exists. "Whose sewage was in my water"
    is a question about YOUR town."""
    assert not any(key == "rivers" for key, _label, _icon in MENU)


def test_the_river_relationship_still_exists_somewhere(page: str) -> None:
    """Removing the tab must not delete the content -- that would be trading
    one failure for another."""
    assert 'data-view="rivers"' in page, "the whole-river view was deleted"
    assert 'data-goto="rivers"' in page, "no way left to reach it"
    assert "discharged upstream of" in page, "the place page lost the relationship"


def test_consolidating_the_menu_deleted_nothing(page: str) -> None:
    """Nine entries became four by MOVING content, not by removing it: the
    findings live as tabs under one entry, Ask Jay lives with the trust story,
    and the read-towns list became the search box's browse mode."""
    for pane in ("silence", "decisions", "disputed", "frontier"):
        assert f'data-fpane="{pane}"' in page, f"the {pane} finding was lost"
        assert f'id="{pane}-body"' in page or pane == "disputed", pane
    assert 'id="ask-input"' in page, "Ask Jay was deleted, not relocated"
    assert 'data-view="ask"' not in page, (
        "Ask Jay still has its own menu-level view; on the shared site that "
        "entry errored for every visitor")
    assert 'data-view="record"' not in page, (
        "the duplicate town view is back; one town renderer, not two")


def test_old_addresses_still_work(page: str) -> None:
    """#view=silence and friends predate the four-entry menu; a bookmark or a
    published link must land on the content, not a blank page."""
    assert "LEGACY" in page
    for old in ("record", "ask", "silence", "decisions", "disputed", "frontier"):
        assert f"{old}:" in page, f"legacy key {old} lost its mapping"


def test_the_place_page_answers_before_the_nav_does(page: str) -> None:
    """A visitor should reach something useful by clicking a dot, without
    choosing a tab first."""
    assert "findbar" in page
    # A CLASS, not an id: more than one rendered record may carry it.
    assert 'class="find"' in page


def test_the_browser_reader_is_linked_from_the_front_page(page: str) -> None:
    """The reader is the loop's second step; a page reachable only by typing
    its address is a secret, not a feature."""
    assert 'href="/browser"' in page
