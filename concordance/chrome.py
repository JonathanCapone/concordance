"""The one set of clothes every page wears.

The portal, the in-browser reader, and the standalone artifact pages grew up
at different times and each dressed itself: the live map wore the dark OMEGA
chrome, the reader wore a similar-but-different dark, and the built pages
wore cream paper with a dark variant behind a media query. Three looks, one
project -- "the pages all seem like different websites", which is exactly
what a visitor said.

This module is the single source for the look: the live portal's own palette
and typography, plus the masthead that names the site on every page. Builders
INLINE these (the artifact pages must stay self-contained -- they are opened
from disk and from places that serve no stylesheet), so changing the site's
face means changing this file and regenerating.
"""

from __future__ import annotations

#: The live portal's palette, verbatim. --hit is the accent the whole site
#: keys on; --cold is the muted blue of not-yet-read things on the map. The
#: aliases at the end let older templates keep their own token names while
#: drawing the same colors: --accent was the paper pages' ink-colored accent,
#: --mark their chart marks, --gap the silence page's red.
TOKENS_CSS = (
    ":root{--bg:#04080d;--panel:rgba(255,255,255,.04);--ink:#e8edf2;"
    "--muted:#8b97a4;--faint:#6d7a86;--line:rgba(255,255,255,.10);"
    "--hit:#f0a24a;--cold:#5b7285;--warn:#d99a5b;--bad:#e0736e;"
    "--accent:#f0a24a;--mark:#e8edf2;--gap:#e0736e;"
    "color-scheme:dark}"
)

#: The site's URL, for pages that live outside it. The standalone artifact
#: pages are opened from disk and from repository browsers, where a relative
#: "/#view=..." resolves to nothing; their menu points home instead.
SITE = "https://concordance.jonathancapone.com"

#: The menu, and the argument for its shape. It used to be nine parallel
#: entries -- a map of the modules in the order they were built, twice over:
#: first as module names, then renamed into questions but never restructured.
#: "Find a place" and "One town, in full" answered the same question two
#: ways; "Ask Jay" errored for every visitor of the shared site; "What to
#: read next" ranked reading four slots away from the reader it serves.
#:
#: The site's own story is a loop -- look up a place; if nobody has read it,
#: your browser reads it; the archive verifies; it is there for everyone --
#: so the menu IS the loop, plus the trust that makes the loop safe:
#:
#:   Find a place    the map, the search, and every town's record
#:   Read a town     the in-browser reader, with what-to-read-next as its
#:                   pick list ("browser" is the reader page's address)
#:   What it found   the findings: what stopped, who decided, disagreements,
#:                   and what is within reach of one more document
#:   Can I trust it  precision, verification, refusals -- and Ask Jay, which
#:                   only appears where a local model exists to answer
MENU = [
    ("observe", "Find a place", "M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17Zm0 4.6a3.9 3.9 0 1 1 0 7.8 3.9 3.9 0 0 1 0-7.8Z"),
    ("browser", "Read a town", "M4 5.5h16v13H4Zm0 3.6h16M10.6 12.2l3.8 2.3-3.8 2.3Z"),
    ("findings", "What it found", "M4 19.2V4.8h9.6l6.4 6.4v8H4Zm9.2-13.4v5.4h5.4"),
    ("verify", "Can I trust it", "M5 12.6 9.8 17.4 19 6.6"),
]

#: The masthead's own styles, shared verbatim by every page that shows it.
#: The nav classes match the front page's values exactly -- same paddings,
#: same active state -- because "the same menu" has to mean the same menu.
HEAD_CSS = """
.site-head{display:flex;align-items:center;flex-wrap:wrap;gap:4px 18px;
  padding:9px 18px;border-bottom:1px solid rgba(255,255,255,.09);
  background:rgba(8,12,17,.94)}
.site-head>a{display:flex;align-items:baseline;gap:10px;text-decoration:none;
  color:inherit}
.site-word{font-size:15px;font-weight:600;letter-spacing:.02em}
.site-sub{font-size:11px;color:#7d8996}
.site-nav{display:flex;flex-wrap:wrap;gap:4px}
.site-nav .nav-button{background:none;border:1px solid transparent;
  border-radius:9px;color:var(--muted);padding:7px 9px;cursor:pointer;
  display:flex;align-items:center;gap:7px;text-decoration:none;font:inherit}
.site-nav .nav-button:hover{color:var(--ink);border-color:rgba(255,255,255,.12)}
.site-nav .nav-button.is-active{color:var(--bg);background:var(--hit);
  border-color:var(--hit)}
.site-nav .nav-glyph{width:17px;height:17px}
.site-nav .nav-tip{font-size:12.5px;font-weight:500}
.site-page{margin-left:auto;font-size:12.5px;color:var(--muted)}
"""


def nav_links(active: str = "", base: str = "") -> str:
    """The site's menu as links, one entry per front-page view plus the
    reader. `base` prefixes every address for pages hosted off-site (the
    standalone artifacts); `active` names the entry this page is."""
    out = ['<nav class="site-nav">']
    for key, label, path in MENU:
        href = f"{base}/browser" if key == "browser" else f"{base}/#view={key}"
        cls = " is-active" if key == active else ""
        out.append(
            f'<a class="nav-button{cls}" href="{href}" aria-label="{label}">'
            f'<svg class="nav-glyph" viewBox="0 0 24 24" aria-hidden="true">'
            f'<path d="{path}" fill="none" stroke="currentColor" '
            f'stroke-width="1.6" stroke-linecap="round" '
            f'stroke-linejoin="round"/></svg>'
            f'<span class="nav-tip">{label}</span></a>'
        )
    out.append("</nav>")
    return "".join(out)

#: Tokens, the app's base typography, and the masthead -- what the served
#: pages inline whole. The standalone longform artifacts keep their own body
#: type (documents read at 16px) and take TOKENS_CSS + HEAD_CSS instead;
#: palette and masthead are the identity, type scale is not.
BASE_CSS = TOKENS_CSS + """
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
""" + HEAD_CSS

#: What an artifact page inlines: the same palette and masthead, no body type.
ARTIFACT_CSS = TOKENS_CSS + HEAD_CSS


def masthead(
    page_label: str = "",
    home: str = "/",
    *,
    active: str = "",
    base: str = "",
) -> str:
    """The site's name and its one menu, on every page.

    `home` and `base` differ by context: pages the live server serves use
    relative addresses; the standalone artifacts pass ``SITE`` for both, so
    their menu still reaches the site when the file is opened from disk.
    `active` marks the menu entry this page is, exactly as the front page
    highlights its current view.
    """
    page = f'<span class="site-page">{page_label}</span>' if page_label else ""
    return (
        f'<header class="site-head"><a href="{home}">'
        f'<span class="site-word">CONCORDANCE</span>'
        f'<span class="site-sub">Canada’s public record, read</span>'
        f"</a>{nav_links(active=active, base=base)}{page}</header>"
    )
