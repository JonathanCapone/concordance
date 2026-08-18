"""Why did each browser record fail? Answer it without running a model.

    python scripts/diagnose_browser_bench.py data/results/browser_bench_shipped.json

Every record the reader produced is replayed against three questions:

  1. did the page's own quote check accept it?
  2. did the page's own value check accept it?
  3. would the SERVER have accepted it -- contribute._value_in_quote, the
     referee that actually decides what gets published?

Question 3 is the one worth asking. The browser's checks are a pre-filter in
front of the server's verifier, and a pre-filter that is STRICTER than the
check it fronts for silently throws away records the archive would have
stood behind. That has happened once already in this project, with values
the page spells "0.20" and the model reads as 0.2.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from concordance.archive import Archive              # noqa: E402
from concordance.contribute import _match_evidence_span, _value_in_quote  # noqa: E402


def norm(s: str) -> str:
    """The browser's `norm`, ported exactly."""
    return re.sub(r"[^a-z0-9.]+", " ", str(s or "").lower()).strip()


def _join_split_numbers(x: str) -> str:
    x = re.sub(r"(\d),\s+(?=\d)", r"\1,", str(x or ""))
    return re.sub(r"(\d)\.\s+(?=\d)", r"\1.", x)


def quote_on_page(quote: str, page_text: str) -> bool:
    """The browser's `quoteOnPage`, ported exactly."""
    def for_match(x: str) -> str:
        joined = norm(_join_split_numbers(x))
        return re.sub(r"\s+", " ", re.sub(r"(?<!\d)\.(?!\d)", " ", joined)).strip()
    q, p = for_match(quote), for_match(page_text)
    return len(q) > 8 and q[:160] in p


def value_in_quote(value, quote: str):
    """The browser's `valueInQuote`, ported exactly (including the numeric
    fallback added after the first live run)."""
    if value is None:
        return None
    canon = str(value)
    if canon.endswith(".0"):
        canon = canon[:-2]
    direct = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", str(quote or ""))
    if re.search(r"(?<![\d.+-])" + re.escape(canon) + r"(?!\d)(?!\.\d)", direct):
        return True
    try:
        n = float(value)
    except (TypeError, ValueError):
        return False
    for tok in re.findall(r"(?<![\d.+-])(?:\d+(?:\.\d+)?|\.\d+)(?!\d)(?!\.\d)", direct):
        if float(tok) == n:
            return True
    joined = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "",
             re.sub(r"(\d)\.\s+(?=\d)", r"\1.",
             re.sub(r"(\d),\s+(?=\d)", r"\1,", str(quote or ""))))
    for tok in re.findall(r"(?<![\d.+-])(?:\d+(?:\.\d+)?|\.\d+)(?!\d)(?!\.\d)", joined):
        if float(tok) == n:
            return True
    WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
             "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
             "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
             "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
             "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
             "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
             "ninety": 90, "hundred": 100, "thousand": 1000}
    if any(WORDS.get(w) == n for w in norm(quote).split(" ")):
        return True
    return False


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    bench = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    archive = Archive()

    counts = {"published": 0, "no quote": 0, "quote not on page": 0,
              "value not in quote": 0}
    stricter_than_server = []

    for pr in bench["pages"]:
        pages = {p.page: p for p in archive.pages(pr["identifier"])}
        page_text = pages[int(pr["page"])].text
        print(f"\n=== {pr['identifier']} p.{pr['page']} "
              f"({len(pr['records'])} records) ===")

        for r in pr["records"]:
            quote = str(r.get("source_text") or "")
            value = r.get("value")
            if isinstance(value, str):
                try:
                    value = float(value)
                except ValueError:
                    pass

            on_page = quote_on_page(quote, page_text)
            in_quote = value_in_quote(value, quote)
            passed = bool(quote) and on_page and in_quote is not False

            if passed:
                counts["published"] += 1
                continue
            why = ("no quote" if not quote
                   else "quote not on page" if not on_page
                   else "value not in quote")
            counts[why] += 1

            # What would the server say? It matches the quote against the page
            # with OCR-tolerant tokenisation, then checks the value against the
            # span it actually found.
            span = _match_evidence_span(quote, page_text)
            if span is None:
                verdict = "server: also cannot find the sentence"
            else:
                state, detail = _value_in_quote(value, span)
                verdict = f"server: {state}" + (f" ({detail[:60]})" if detail else "")
                if state in ("ok", "unchecked"):
                    stricter_than_server.append((pr["page"], r, verdict))

            print(f"  REFUSED [{why}] {r.get('parameter')} = {r.get('value')} "
                  f"{r.get('unit') or ''}")
            print(f"     quote: {quote[:96]}")
            print(f"     {verdict}")

    print("\n---- totals ----")
    for k, v in counts.items():
        print(f"  {k:20s} {v}")

    if stricter_than_server:
        print(f"\n**{len(stricter_than_server)} record(s) the browser refused that "
              f"the SERVER would have accepted.**")
        print("The pre-filter is stricter than the referee it fronts for:")
        for page, r, verdict in stricter_than_server:
            print(f"  p.{page}: {r.get('parameter')} = {r.get('value')}  [{verdict}]")
    else:
        print("\nNo record was refused here that the server would have accepted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
