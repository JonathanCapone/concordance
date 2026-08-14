"""The page's JavaScript must actually parse.

813 tests passed against a portal where nothing loaded at all. One escape in
one string literal -- a `\n` written into a Python f-string, which evaluates to
a real newline and lands inside a JS string -- was a syntax error, and a syntax
error takes EVERY handler on the page with it. The map, the town panel, the
filter, the reader: all dead, and every existing test still green, because they
all assert on the HTML as text.

This is the same family as the control-byte trap in test_vision: a character
that survives every reading of the source and destroys the artifact.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

import concordance.server as S


def _blocks() -> list[str]:
    page = S.State().html()
    return re.findall(r"<script>(.*?)</script>", page, re.S)


def test_there_is_script_to_check() -> None:
    blocks = _blocks()
    assert blocks and sum(len(b) for b in blocks) > 1000


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
def test_every_inline_script_parses() -> None:
    for i, js in enumerate(_blocks()):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(js)
            path = fh.name
        try:
            result = subprocess.run(["node", "--check", path],
                                    capture_output=True, text=True, timeout=60)
        finally:
            Path(path).unlink(missing_ok=True)
        assert result.returncode == 0, (
            f"inline script {i} does not parse:\n{result.stderr[:600]}")


def test_the_parse_check_is_actually_running() -> None:
    """Guard the guard.

    The real check is `node --check`, which is exact. Two earlier attempts at a
    pure-Python fallback both produced false positives -- one counted quotes
    per line and tripped over `.replace(/"/g, ...)`, a regex literal containing
    a quote. A test that pretends to parse a language it does not parse is
    worse than no test, so the fallback is gone and this asserts instead that
    the real check is available here rather than silently skipping forever.
    """
    assert shutil.which("node"), (
        "node is not installed, so the JavaScript is NOT being parse-checked. "
        "813 tests once passed against a portal where nothing loaded at all."
    )
