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
#:   Can I trust it  precision, verification, refusals
#:   Ask Jay         the agent over the whole record -- a name, not a module,
#:                   and not buried inside another page; its view says up
#:                   front where it answers (a local machine) instead of
#:                   erroring after the question is typed
MENU = [
    ("observe", "Find a place", "M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17Zm0 4.6a3.9 3.9 0 1 1 0 7.8 3.9 3.9 0 0 1 0-7.8Z"),
    ("browser", "Read a town", "M4 5.5h16v13H4Zm0 3.6h16M10.6 12.2l3.8 2.3-3.8 2.3Z"),
    ("findings", "What it found", "M4 19.2V4.8h9.6l6.4 6.4v8H4Zm9.2-13.4v5.4h5.4"),
    ("verify", "Can I trust it", "M5 12.6 9.8 17.4 19 6.6"),
    ("ask", "Ask Jay", "M4.5 6.5h15v9h-8.4L6.6 19v-3.5H4.5Z"),
]

#: The masthead's own styles -- the ONE header, used by every page including
#: the front one. It used to be two: the map page rendered its own
#: `app-header` (a fixed 210px brand block and a nav carrying the inherited
#: `icon-nav` class, which restyles buttons into tall icon-over-tiny-label
#: form) while everything else rendered this. Measured, the first menu item
#: sat at x=252 on the front page and x=298 everywhere else, 48px tall
#: against 35px -- so the menu jumped sideways and changed size the moment
#: you left the map. Selectors here are deliberately specific enough to win
#: against the inherited stylesheet without needing !important.
HEAD_CSS = """
.site-head{display:flex;align-items:center;align-content:flex-start;
  flex-wrap:wrap;gap:4px 18px;padding:9px 18px;
  border-bottom:1px solid rgba(255,255,255,.09);background:rgba(8,12,17,.94)}
.site-head>a.site-brand{display:flex;align-items:baseline;gap:10px;
  text-decoration:none;color:inherit;flex:0 0 auto}
.site-word{font-size:15px;font-weight:600;letter-spacing:.02em}
.site-sub{font-size:11px;color:#7d8996}
.site-head .site-nav{display:flex;flex-wrap:wrap;gap:4px;align-items:center}
.site-head .site-nav .nav-button{background:none;border:1px solid transparent;
  border-radius:9px;color:var(--muted);padding:7px 9px;cursor:pointer;
  display:flex;align-items:center;gap:7px;text-decoration:none;font:inherit;
  font-size:15px;line-height:1.55;width:auto;height:auto;min-height:0;
  min-width:0;flex-direction:row;transform:none;transition:none}
.site-head .site-nav .nav-button:hover{color:var(--ink);
  border-color:rgba(255,255,255,.12);transform:none}
/* The inherited sheet lifts a nav button and scales its icon on hover. In a
   header this size that reads as the menu twitching, so both are stilled. */
.site-head .site-nav .nav-button:hover .nav-glyph{transform:none}
.site-head .site-nav .nav-button.is-active{color:var(--bg);background:var(--hit);
  border-color:var(--hit)}
.site-head .site-nav .nav-glyph{width:17px;height:17px;flex:0 0 auto}
/* `.nav-tip` is a hover TOOLTIP in the inherited stylesheet -- absolutely
   positioned, transparent, with its own background and border. Left partly
   overridden it made the front page's menu icon-only while every other page
   showed icon and label. Every tooltip property is undone here, so the label
   is an ordinary word beside its icon on every page. */
.site-head .site-nav .nav-tip{position:static;top:auto;left:auto;
  transform:none;opacity:1;padding:0;border:0;background:none;color:inherit;
  font-size:12.5px;font-weight:500;letter-spacing:normal;text-transform:none;
  white-space:nowrap;pointer-events:auto;transition:none;display:inline}
.site-page{margin-left:auto;font-size:12.5px;color:var(--muted)}
.site-stats{margin-left:auto;display:flex;gap:0;
  border:1px solid rgba(255,255,255,.10);border-radius:9px;overflow:hidden}
.site-stats .hstat{padding:5px 13px;border-right:1px solid rgba(255,255,255,.10)}
.site-stats .hstat:last-child{border-right:0}
.site-stats .hstat b{display:block;font-size:15px;font-weight:600;
  font-variant-numeric:tabular-nums;line-height:1.2}
.site-stats .hstat span{font-size:9.5px;color:var(--faint);
  text-transform:uppercase;letter-spacing:.06em}
/* The counts are the only thing that differs between this header and every
   other one, so they are the only thing allowed to disappear. Below this
   width they would wrap to a second row and push the menu off the line it
   sits on everywhere else -- which is the jump this whole change removes. */
@media(max-width:1500px){.site-stats{display:none}}
"""


def nav_links(active: str = "", base: str = "") -> str:
    """The site's menu, identical on every page: the same elements, in the
    same order, at the same size.

    Links rather than buttons even on the front page, where the click is
    intercepted and switches the view in place -- so one markup serves both
    "go to the site's map view" and "show that view now". `data-view` lets
    the front page's own highlighting keep working unchanged; `base`
    prefixes addresses for pages hosted off-site (the standalone artifacts);
    `active` names the entry this page IS.
    """
    out = ['<nav class="site-nav" aria-label="Sections">']
    for key, label, path in MENU:
        href = f"{base}/browser" if key == "browser" else f"{base}/#view={key}"
        cls = " is-active" if key == active else ""
        out.append(
            f'<a class="nav-button{cls}" href="{href}" data-view="{key}" '
            f'aria-label="{label}">'
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
    stats: list[tuple[str, str]] | None = None,
) -> str:
    """The site's name and its one menu -- the same header on every page.

    `home` and `base` differ by context: pages the live server serves use
    relative addresses; the standalone artifacts pass ``SITE`` for both, so
    their menu still reaches the site when the file is opened from disk.
    `active` marks the menu entry this page is. `stats` is the front page's
    headline count row; it renders inside this same header rather than in a
    second one, which is how the two headers became one.
    """
    tail = ""
    if stats:
        cells = "".join(
            f"<div class='hstat'><b>{value}</b><span>{label}</span></div>"
            for value, label in stats
        )
        tail = f'<div class="site-stats">{cells}</div>'
    elif page_label:
        tail = f'<span class="site-page">{page_label}</span>'
    return (
        f'<header class="site-head"><a class="site-brand" href="{home}">'
        f'<span class="site-word">CONCORDANCE</span>'
        f'<span class="site-sub">Canada’s public record, read</span>'
        f"</a>{nav_links(active=active, base=base)}{tail}</header>"
    )
