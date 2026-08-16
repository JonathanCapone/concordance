"""The navigation names questions a visitor has, not modules I built.

The complaint that started this: "Why is there a river tab? ... I didn't really
understand what the tabs were for or how I would actually use any of the
information." The nine tabs were Observe, Record, Silence, Rivers, Verify,
Frontier, Decisions, Disputed, Ask Jay -- the modules, in build order.
"""

from __future__ import annotations

import pytest

import concordance.server as S
from concordance.portal import NAV


@pytest.fixture(scope="module")
def page() -> str:
    return S.State().html()


def test_rivers_is_not_a_top_level_idea() -> None:
    """It was a tab because watershed.py exists. "Whose sewage was in my water"
    is a question about YOUR town."""
    assert not any(key == "rivers" for key, _label, _icon in NAV)


def test_the_river_relationship_still_exists_somewhere(page: str) -> None:
    """Removing the tab must not delete the content -- that would be trading
    one failure for another."""
    assert 'data-view="rivers"' in page, "the whole-river view was deleted"
    assert 'data-goto="rivers"' in page, "no way left to reach it"
    assert "discharged upstream of" in page, "the place page lost the relationship"


def test_no_tab_is_named_after_a_module() -> None:
    stale = {"observe", "record", "silence", "rivers", "verify",
             "frontier", "decisions", "disputed"}
    labels = {label.lower() for _key, label, _icon in NAV}
    assert not (labels & stale), f"module names still in the nav: {labels & stale}"


def test_no_label_is_just_its_view_key(page: str) -> None:
    """The old nav's failing was that every label WAS the module behind it.

    An earlier version of this test demanded two words per label, which is a
    proxy rather than the property -- it rejected "Disagreements", which is a
    perfectly plain outcome word, while accepting any two-word module name. The
    real invariant is that a label is chosen for the reader rather than
    inherited from the code.
    """
    for key, label, _icon in NAV:
        assert label.lower() != key.lower(), (
            f"{label!r} is just the view key {key!r}")


def test_the_place_page_answers_before_the_nav_does(page: str) -> None:
    """A visitor should reach something useful by clicking a dot, without
    choosing a tab first."""
    assert "findbar" in page
    # A CLASS, not an id: the dock and the whole-record view both render this,
    # and an id can only ever bind the first one on the page.
    assert 'class="find"' in page


def test_the_browser_reader_is_linked_from_the_front_page() -> None:
    """The in-browser reader is the project's proof that no install is
    needed; a demo reachable only by typing its address is a secret, not a
    feature. The front page must link it."""
    import concordance.server as server

    html = server.State().html()
    assert 'href="/browser"' in html


def test_the_browser_reader_is_linked_from_the_front_page() -> None:
    """The in-browser reader is the project's proof that no install is
    needed; a demo reachable only by typing its address is a secret, not a
    feature. The front page must link it."""
    import concordance.server as server

    html = server.State().html()
    assert 'href="/browser"' in html
