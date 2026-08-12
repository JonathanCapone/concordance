"""Show the piece of paper the number came from.

Every record in this project already carries a page and the sentence it was read
from. That is enough for a person to go and check -- but "go and check" means
opening a scan of a 300-page report and hunting for a line, which nobody does.
So in practice the provenance is real and unused, which is most of the way to
not having it.

This turns the citation into a picture: the exact region of the exact scan where
the number is written, cropped and shown next to the number. Checking stops being
a task and becomes a glance.

**It costs nothing and needs nothing.** archive.org serves IIIF level 2 for these
items, so a crop is a URL -- no image library, no processing, no storage, no key,
and no server of ours in the path. Better still, the coordinate space in the
`_djvu.xml` word list is the *same* space IIIF serves -- Owen Sound page 10 is
2814x3739 in both -- so word boxes become crop rectangles with no scaling and no
calibration constant to get wrong.

That last fact is also the trap. The two archive.org endpoints number the same
sheet differently: BookReader `n14` and IIIF `$15` are both the Brantford 1962
flow table. Feed one index to the other and the crop is of the previous leaf,
which is a citation pointing confidently at the wrong page. The dimensions are
the tell -- they match only when the index is right -- but on an item whose
leaves are all the same size they match anyway, so this was settled by fetching
both pages and looking at them.

Two kinds of evidence, because the two extraction paths leave different traces:

* **Prose** -- the words of the quoted sentence are in the OCR word list, so the
  crop is their bounding box. Exact.
* **Tables** -- the value itself is usually NOT in the word list, because failing
  to read those numbers is why the vision path exists at all. But the row and
  column labels normally survive, and the vision extractor already records them
  ("table cell [Jan. / MAX. DAILY Flow]"). The cell is the intersection: the row
  label's band of rows, the column header's band of columns.

When neither works the citation degrades to the whole page and says so. A crop
that silently points at the wrong place would be worse than no crop, because a
picture is believed in a way a line number is not.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .models import PageText, Word

#: The public shorthand. It answers for metadata and redirects, but the image
#: endpoint will not accept it -- that wants the canonical id, which spells out
#: the path into the item's jp2 archive and the zero-padded leaf name. The
#: shorthand 404s there, silently, and a citation that 404s is worse than none.
INFO = "https://iiif.archive.org/iiif/3/{ident}${index}/info.json"

#: Where the canonical ids are kept, since resolving one costs a request and a
#: page's citation is asked for many times.
CACHE = Path("data/cache/iiif")

_MEMO: dict[tuple[str, int], str | None] = {}


def iiif_base(identifier: str, index: int, *, timeout: float = 30.0) -> str | None:
    """Resolve the canonical IIIF id for a page, or None if it has no scan.

    Resolved rather than constructed. The obvious guess --
    `{id}%2f{id}_jp2.zip%2f{id}_jp2%2f{id}_0014.jp2` -- is right for most items
    and wrong for the ones packed as a tar, derived from a PDF, or scanned under
    a different leaf name, and the failure mode is a broken image rather than an
    error anybody would notice.
    """
    key = (identifier, index)
    if key in _MEMO:
        return _MEMO[key]

    path = CACHE / f"{identifier}.json"
    store: dict[str, str] = {}
    if path.exists():
        try:
            store = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            store = {}
    if str(index) in store:
        _MEMO[key] = store[str(index)]
        return _MEMO[key]

    try:
        request = urllib.request.Request(
            INFO.format(ident=identifier, index=index),
            headers={"User-Agent": "ground-truth/0.1"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            info = json.loads(response.read().decode())
        base = info.get("id") or info.get("@id")
    except Exception:  # noqa: BLE001
        base = None

    _MEMO[key] = base
    if base:
        store[str(index)] = base
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(store), encoding="utf-8")
    return base

#: Whitespace left around a crop, in image pixels. A box drawn tightly on the
#: matched words is hard to read: the eye needs the line above and below to see
#: that the crop was not cut out of context.
PAD = 26

#: Widest crop returned, in pixels. Keeps a citation loading quickly on a phone.
MAX_WIDTH = 1200

#: A cell crop is built from two labels that may be far apart, and if either is
#: matched wrongly the rectangle can swell to most of the page. Past this share
#: of the page the crop is not evidence of anything and the citation says so.
MAX_CELL_AREA = 0.25


@dataclass
class Citation:
    """Where a number is written down, as a picture and as a link."""

    identifier: str
    page: int
    quote: str = ""
    box: tuple[int, int, int, int] | None = None    # x, y, w, h in image space
    kind: str = "page"                              # quote | cell | page
    note: str = ""

    @property
    def leaf(self) -> int:
        """The BookReader's index for this page. Zero-based."""
        return max(0, self.page - 1)

    @property
    def iiif_index(self) -> int:
        """The IIIF service's index for the same physical page. One-based.

        The two archive.org endpoints number the same sheet differently, and
        nothing says so. BookReader `n14` and IIIF `$15` are both the Brantford
        1962 flow table; feeding the BookReader's number to IIIF returns the
        preceding leaf, which is a citation that points confidently at the wrong
        page -- the worst thing this module could do, because a picture is
        believed in a way a page number is not.

        Verified by fetching both and looking at them, which is the only way
        this could have been settled: the OCR page dimensions match the IIIF
        leaf exactly once the index is right (2814x3739 for Owen Sound page 10),
        and they disagree when it is off by one.
        """
        return self.page

    @property
    def page_url(self) -> str:
        return (f"https://archive.org/details/{self.identifier}"
                f"/page/n{self.leaf}/mode/2up")

    def _url(self, region: str, size: str) -> str:
        base = iiif_base(self.identifier, self.iiif_index)
        if not base:
            return self.page_url          # no scan to point at; the reader link stands
        return f"{base}/{region}/{size}/0/default.jpg"

    @property
    def image_url(self) -> str:
        return self._url("full", f"{MAX_WIDTH},")

    @property
    def crop_url(self) -> str:
        """The evidence itself, cropped out of the scan."""
        if not self.box:
            return self.image_url
        x, y, w, h = self.box
        size = f"{MAX_WIDTH}," if w > MAX_WIDTH else "max"
        return self._url(f"{x},{y},{w},{h}", size)

    @property
    def exact(self) -> bool:
        return self.box is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "identifier": self.identifier, "page": self.page,
            "quote": self.quote, "kind": self.kind, "exact": self.exact,
            "box": list(self.box) if self.box else None,
            "crop_url": self.crop_url, "image_url": self.image_url,
            "page_url": self.page_url, "note": self.note,
        }


def _bounds(words: Iterable[Word], page: PageText, *, pad: int = PAD) -> tuple[int, int, int, int]:
    ws = list(words)
    x0 = max(0, min(w.x0 for w in ws) - pad)
    y0 = max(0, min(w.y0 for w in ws) - pad)
    x1 = max(w.x1 for w in ws) + pad
    y1 = max(w.y1 for w in ws) + pad
    if page.width:
        x1 = min(x1, page.width)
    if page.height:
        y1 = min(y1, page.height)
    return (x0, y0, x1 - x0, y1 - y0)


def cite(page: PageText, quote: str, *, pad: int = PAD) -> Citation:
    """Crop the sentence a value was read from, however many lines it runs to.

    `find_boxes` returns a contiguous run of words, and degrades to the longest
    matching *opening* run when the whole phrase does not match — which it
    frequently does not, because OCR mangles the middle of a sentence more often
    than its start. Cropping to that run alone produced citations reading "It is
    seen that the C", which is the right sentence and useless as evidence.

    So the end of the quote is located as well as the beginning, and the crop
    spans both. A sentence that wraps then covers several lines, and the crop is
    widened to the full column so the intervening lines are not sliced down the
    middle.
    """
    if not quote:
        return Citation(identifier=page.identifier, page=page.page, kind="page",
                        note="no sentence was recorded for this reading")

    head = page.find_boxes(quote)
    if not head:
        return Citation(
            identifier=page.identifier, page=page.page, quote=quote, kind="page",
            note="the words of this quote are not in the page's OCR, so the "
                 "citation shows the whole page",
        )

    words = list(head)
    tail_words = [t for t in re.split(r"\W+", quote) if t][-6:]
    if len(tail_words) >= 3:
        tail = page.find_boxes(" ".join(tail_words))
        # Only if it lands after the head: a phrase repeated earlier on the page
        # would otherwise stretch the crop backwards over unrelated text.
        if tail and min(w.y0 for w in tail) >= min(w.y0 for w in head):
            words += tail

    box = _bounds(words, page, pad=pad)
    return Citation(identifier=page.identifier, page=page.page, quote=quote,
                    box=_widen_to_column(box, page, pad=pad), kind="quote")


def _widen_to_column(
    box: tuple[int, int, int, int],
    page: PageText,
    *,
    pad: int = PAD,
) -> tuple[int, int, int, int]:
    """Stretch a crop sideways to hold every word on the lines it covers.

    A quote that wraps occupies whole lines, and a box drawn only around the
    words that happened to match cuts the lines between them in half. Widening
    to the text actually present on those lines shows the passage as it sits on
    the page, which is what a reader is checking against.
    """
    x, y, w, h = box
    if not page.words:
        return box
    on_lines = [word for word in page.words
                if word.y1 >= y and word.y0 <= y + h]
    if not on_lines:
        return box
    x0 = max(0, min(word.x0 for word in on_lines) - pad)
    x1 = max(word.x1 for word in on_lines) + pad
    if page.width:
        x1 = min(x1, page.width)
    # Never narrower than what matched, and never the whole page either.
    x0, x1 = min(x0, x), max(x1, x + w)
    return (x0, y, x1 - x0, h)


#: How the vision path writes a cell reference.
CELL_RE = re.compile(r"table cell\s*\[\s*(.+?)\s*/\s*(.+?)\s*\]", re.I)


def _find_label(page: PageText, label: str) -> list[Word]:
    """Locate a heading, allowing that the model reads it better than OCR did.

    This is the awkward seam of the whole idea. The vision model returns the
    heading as it appears on the *scan* -- "MAX. DAILY Flow" -- while the word
    list holds what 2013 OCR made of it, "MAX. DAILY r low". The correct label
    therefore fails to match the page it was correctly read from, which is a
    peculiar way to lose.

    So the label is shortened a token at a time from the right until something
    matches: "MAX. DAILY Flow", then "MAX. DAILY", then "MAX.". A shorter match
    is a wider crop, never a wrong one, because every prefix of a heading starts
    in the same place on the page.
    """
    tokens = [t for t in re.split(r"\W+", label) if t]
    for cut in range(len(tokens), 0, -1):
        found = page.find_boxes(" ".join(tokens[:cut]))
        if found:
            return found
    return []


def cite_cell(
    page: PageText,
    row_label: str,
    column_label: str,
    *,
    pad: int = PAD,
) -> Citation:
    """Crop a table cell from the labels that name it.

    The value is generally absent from the word list -- OCR's failure to read
    those numbers is the entire reason for the vision path -- but the labels
    usually survive. So the cell is found the way a person finds it: run a
    finger along the row, down from the heading, and take the crossing.
    """
    rows = _find_label(page, row_label)
    cols = _find_label(page, column_label)
    if not rows or not cols:
        missing = "row" if not rows else "column"
        return Citation(
            identifier=page.identifier, page=page.page,
            quote=f"{row_label} / {column_label}", kind="page",
            note=f"the {missing} label is not in the page's OCR, so the citation "
                 "shows the whole page",
        )

    y0 = max(0, min(w.y0 for w in rows) - pad)
    y1 = max(w.y1 for w in rows) + pad
    x0 = max(0, min(w.x0 for w in cols) - pad)
    x1 = max(w.x1 for w in cols) + pad
    if page.width:
        x1 = min(x1, page.width)
    if page.height:
        y1 = min(y1, page.height)

    box = (x0, y0, max(1, x1 - x0), max(1, y1 - y0))
    if page.width and page.height:
        share = (box[2] * box[3]) / float(page.width * page.height)
        if share > MAX_CELL_AREA:
            # A label matched in the wrong place, and the rectangle has swollen
            # to most of the page. That is not evidence, and cropping to it
            # would dress a failure up as a citation.
            return Citation(
                identifier=page.identifier, page=page.page,
                quote=f"{row_label} / {column_label}", kind="page",
                note=f"the row and column labels enclose {share:.0%} of the page, "
                     "too much to be one cell, so the citation shows the whole page",
            )
    return Citation(identifier=page.identifier, page=page.page,
                    quote=f"{row_label} / {column_label}", box=box, kind="cell")


def cite_record(page: PageText, record: dict[str, Any], *, pad: int = PAD) -> Citation:
    """Cite whatever kind of evidence this record happens to carry."""
    provenance = record.get("provenance") or {}
    source = str(provenance.get("source_text") or "")
    cell = CELL_RE.search(source)
    if cell:
        return cite_cell(page, cell.group(1), cell.group(2), pad=pad)
    return cite(page, source, pad=pad)
