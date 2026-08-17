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

#: The masthead's own styles, shared verbatim by every page that shows it.
HEAD_CSS = """
.site-head{display:flex;align-items:baseline;gap:10px;padding:9px 18px;
  border-bottom:1px solid rgba(255,255,255,.09);background:rgba(8,12,17,.94)}
.site-head a{display:flex;align-items:baseline;gap:10px;text-decoration:none;
  color:inherit}
.site-word{font-size:15px;font-weight:600;letter-spacing:.02em}
.site-sub{font-size:11px;color:#7d8996}
.site-page{margin-left:auto;font-size:12.5px;color:var(--muted)}
"""

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


def masthead(page_label: str = "", home: str = "/") -> str:
    """The site's name, on every page, linking back to the site.

    `home` differs by context: the live server's pages point at "/", the
    standalone artifacts point at their own index so the link still works
    opened from a folder.
    """
    page = f'<span class="site-page">{page_label}</span>' if page_label else ""
    return (
        f'<header class="site-head"><a href="{home}">'
        f'<span class="site-word">CONCORDANCE</span>'
        f'<span class="site-sub">Canada’s public record, read</span>'
        f"</a>{page}</header>"
    )
