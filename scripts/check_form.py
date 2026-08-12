"""Check every answer against the form's own character limits.

The BC + AI application is eight free-text boxes, not a document. Seven allow
2,000 characters and the success metric allows 600. An answer that overruns is
not a style problem -- the form truncates or refuses it, and the reviewer reads
whatever survived.

    python scripts/check_form.py

Counts the rendered answer, not the markdown source: headings, the limit
annotations and the rule lines are scaffolding for me and are not pasted in.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

LIMITS = {
    "Project summary": 2000,
    "Public benefit": 2000,
    "Proposed approach": 2000,
    "Dataset interest": 2000,
    "Work plan": 2000,
    "Expected deliverable": 2000,
    "Success metric": 600,
    "Relevant experience": 2000,
}

FORM = Path(__file__).resolve().parents[1] / "APPLICATION-FORM.md"


def answers(text: str) -> dict[str, str]:
    """Split on the level-2 headings and strip the scaffolding."""
    out: dict[str, str] = {}
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        head, _, body = block.partition("\n")
        # "Public benefit — *Who could...* (2000)" -> "Public benefit"
        name = re.split(r"\s+[—-]\s+|\s+\(", head.strip())[0].strip()
        body = body.replace("---", "").strip()
        out[name] = body
    return out


def plain(markdown: str) -> str:
    """What actually goes in the box, as the form will count it."""
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", markdown, flags=re.S)   # bold
    t = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", t, flags=re.S)  # italic
    t = re.sub(r"`(.+?)`", r"\1", t, flags=re.S)                 # code
    return t.strip()


def main() -> int:
    if not FORM.exists():
        print(f"missing {FORM}")
        return 1

    found = answers(FORM.read_text(encoding="utf-8"))
    worst = 0
    print(f"{'field':<24}{'chars':>7}{'limit':>7}{'':>4}")
    print("-" * 46)

    for field, limit in LIMITS.items():
        body = found.get(field)
        if body is None:
            print(f"{field:<24}{'MISSING':>7}{limit:>7}   !")
            worst = 2
            continue
        n = len(plain(body))
        over = n - limit
        flag = "  OVER" if over > 0 else ("  tight" if over > -120 else "")
        if over > 0:
            worst = max(worst, 1)
        print(f"{field:<24}{n:>7}{limit:>7}{flag}")

    extra = sorted(set(found) - set(LIMITS) - {"Project title"})
    if extra:
        print(f"\nnot form fields (fine, but not pasted anywhere): {', '.join(extra)}")

    print()
    if worst == 0:
        print("every answer fits.")
    elif worst == 1:
        print("SOMETHING IS OVER THE LIMIT. The form will cut it, not wrap it.")
    return worst if worst != 2 else 1


if __name__ == "__main__":
    sys.exit(main())
