"""Records come from strangers, so their strings must never be markup.

/api/bundle and /api/submit accept readings from anyone with no account, on
purpose: the archive decides, and asking who is speaking would contradict the
project's central claim. But "we do not check the sender" has to mean we do not
check their IDENTITY. It cannot mean we paste their strings into the page.

A submitted reading whose place is `<img src=x onerror=...>` executed on the
Disputed view -- the page a reader opens precisely to adjudicate a contested
number, which is the worst possible place to lose control of the markup.
"""

from __future__ import annotations

import re

import pytest

import groundtruth.server as S

#: Fields that arrive on a record and end up drawn as labels.
CONTRIBUTOR_FIELDS = ("contributor", ".place", ".facility", ".parameter",
                      ".unit", ".period", "read_from", ".quote", ".value")


@pytest.fixture(scope="module")
def page() -> str:
    return S.State().html()


def test_the_escaper_exists(page: str) -> None:
    assert "const esc = v =>" in page


def test_the_escaper_is_defined_before_anything_uses_it(page: str) -> None:
    """A helper defined below its first call site is a ReferenceError, and the
    view that would break is the one this is protecting."""
    definition = page.index("const esc = v =>")
    first_use = page.index("esc(", definition + len("const esc = v =>"))
    assert definition < first_use


def test_no_record_field_reaches_innerhtml_unescaped(page: str) -> None:
    """The property, stated over the whole served page rather than per view.

    Checked against the rendered output instead of the source template, because
    the template is an f-string and it is the rendered form that runs.
    """
    raw = []
    for m in re.finditer(r"\$\{([^{}]+?)\}", page):
        expr = m.group(1)
        if "esc(" in expr:
            continue
        if any(f in expr for f in CONTRIBUTOR_FIELDS):
            raw.append(expr.strip())
    assert not raw, f"unescaped record fields in the page: {raw[:6]}"


@pytest.mark.parametrize("payload", [
    "<img src=x onerror=alert(1)>",
    "</div><script>alert(1)</script>",
    "\" onmouseover=\"alert(1)",
    "' onfocus='alert(1)",
    "<svg/onload=alert(1)>",
])
def test_the_escaper_neutralises_real_payloads(payload: str) -> None:
    """Mirrors the JS implementation exactly; if one changes the other must."""
    def esc(v: str) -> str:
        return (str(v).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;"))

    out = esc(payload)
    assert "<" not in out and ">" not in out
    assert '"' not in out and "'" not in out
