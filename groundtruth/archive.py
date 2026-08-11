"""Internet Archive adapter.

Reads the `governmentpublications` collection -- 104,241 items, 22.1 million
scanned pages, roughly 59 GB of OCR text. Everything here is cached to disk and
resumable, because a full pass takes days and archive.org is a charity whose
bandwidth we are borrowing.

Design notes:

* Pages, not documents. 55.3% of items are *mixed* -- narrative sections and
  appendix tables in the same file -- so anything that classifies at document
  level throws away half the data.
* Page boundaries come from `_djvu.xml`, NOT from form feeds. The plain
  `_djvu.txt` export contains no page markers whatsoever (verified: zero form
  feeds across sampled items), so splitting on them silently collapses a
  500-page report into a single page and destroys provenance. The XML also
  carries word coordinates, which is what lets a claim be highlighted *on* the
  scan rather than merely linked to it.
* Nothing here calls a model. This module only fetches and splits; extraction
  lives in `extract.py` behind the router.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .models import PageText, Word

COLLECTION = "governmentpublications"
_SCRAPE = "https://archive.org/services/search/v1/scrape"
_META = "https://archive.org/metadata"
_DOWNLOAD = "https://archive.org/download"

#: Identify ourselves. archive.org is a nonprofit; anonymous hammering is rude
#: and gets you rate-limited anyway.
USER_AGENT = "ground-truth/0.1 (+https://archive.org/details/governmentpublications)"

INDEX_FIELDS = (
    "identifier,title,year,date,language,subject,collection,"
    "publisher,imagecount,downloads,item_size"
)


class ArchiveError(RuntimeError):
    pass


def _get(url: str, *, timeout: float = 180.0, retries: int = 4) -> bytes:
    """Fetch with backoff. Transient 5xx and timeouts are normal at this scale."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            # 404 will never succeed on retry; don't waste the archive's time.
            if exc.code == 404:
                raise ArchiveError(f"not found: {url}") from exc
            last = exc
        except Exception as exc:  # noqa: BLE001 - network layer, anything goes
            last = exc
        time.sleep(2 ** attempt)
    raise ArchiveError(f"failed after {retries} attempts: {url} ({last})")


class Archive:
    """Cached access to one Internet Archive collection.

    Every network result lands on disk before it is used, so a run that dies in
    hour nine resumes in second one.
    """

    def __init__(self, cache_dir: str | Path = "data/cache", collection: str = COLLECTION) -> None:
        self.collection = collection
        self.cache = Path(cache_dir)
        (self.cache / "meta").mkdir(parents=True, exist_ok=True)
        (self.cache / "text").mkdir(parents=True, exist_ok=True)

    # -- index ------------------------------------------------------------

    def index_path(self) -> Path:
        return self.cache / f"index_{self.collection}.json"

    def fetch_index(self, *, force: bool = False) -> list[dict[str, Any]]:
        """The whole collection index. ~104k rows; a few minutes cold, instant warm."""
        path = self.index_path()
        if path.exists() and not force:
            return json.loads(path.read_text(encoding="utf-8"))

        items: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params = {
                "q": f"collection:{self.collection}",
                "fields": INDEX_FIELDS,
                "count": "10000",
            }
            if cursor:
                params["cursor"] = cursor
            payload = json.loads(_get(f"{_SCRAPE}?{urllib.parse.urlencode(params)}").decode())
            items.extend(payload.get("items", []))
            cursor = payload.get("cursor")
            if not cursor:
                break

        path.write_text(json.dumps(items), encoding="utf-8")
        return items

    def load_index(self) -> list[dict[str, Any]]:
        """Index from disk, fetching only if we've never pulled it."""
        path = self.index_path()
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return self.fetch_index()

    # -- per item ---------------------------------------------------------

    def metadata(self, identifier: str) -> dict[str, Any]:
        path = self.cache / "meta" / f"{identifier}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        data = json.loads(_get(f"{_META}/{identifier}").decode())
        path.write_text(json.dumps(data), encoding="utf-8")
        return data

    def _ocr_filename(self, identifier: str) -> str | None:
        for f in self.metadata(identifier).get("files", []):
            name = f.get("name", "")
            if name.endswith("_djvu.txt"):
                return name
        return None

    def ocr_text(self, identifier: str) -> str | None:
        """Full OCR text for an item, cached. None if the item has no text layer.

        In a 150-item sample every item had one, but 'every item so far' is not
        'every item', so callers must handle None.
        """
        path = self.cache / "text" / f"{identifier}.txt"
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")

        name = self._ocr_filename(identifier)
        if not name:
            return None
        url = f"{_DOWNLOAD}/{identifier}/{urllib.parse.quote(name)}"
        text = _get(url).decode("utf-8", "replace")
        path.write_text(text, encoding="utf-8")
        return text

    # -- pages ------------------------------------------------------------
    #
    # Two-tier by necessity. `_djvu.txt` is ~15 KB/item (59 GB corpus-wide) and
    # is what the cheap filter pass reads -- but it has NO page markers at all,
    # so it cannot carry provenance. `_djvu.xml` is ~271 KB/item (~1 TB
    # corpus-wide, far too much for a full pass) but has real page boundaries
    # *and* word coordinates. So: filter on the text, then pull XML only for the
    # items that earn it.

    def _page_cache(self, identifier: str) -> Path:
        return self.cache / "pages" / f"{identifier}.json"

    def pages(self, identifier: str, *, with_words: bool = False) -> list[PageText]:
        """Real pages, parsed from `_djvu.xml` and cached in compact form.

        The raw XML is discarded after parsing -- keeping it would bloat the
        cache by an order of magnitude for data we have already extracted.
        """
        cache = self._page_cache(identifier)
        cache.parent.mkdir(parents=True, exist_ok=True)

        if cache.exists():
            payload = json.loads(cache.read_text(encoding="utf-8"))
        else:
            payload = self._parse_djvu_xml(identifier)
            if payload is None:
                return self._fallback_pages(identifier)
            cache.write_text(json.dumps(payload), encoding="utf-8")

        out: list[PageText] = []
        for p in payload["pages"]:
            words = (
                [Word(w[0], w[1], w[2], w[3], w[4]) for w in p.get("w", [])]
                if with_words
                else []
            )
            out.append(
                PageText(
                    identifier=identifier,
                    ocr_confidence=p.get("c"),
                    page=p["n"],
                    text=p["t"],
                    width=p.get("W"),
                    height=p.get("H"),
                    words=words,
                )
            )
        return out

    def _parse_djvu_xml(self, identifier: str) -> dict[str, Any] | None:
        name = None
        for f in self.metadata(identifier).get("files", []):
            if f.get("name", "").endswith("_djvu.xml"):
                name = f["name"]
                break
        if not name:
            return None

        try:
            raw = _get(f"{_DOWNLOAD}/{identifier}/{urllib.parse.quote(name)}").decode(
                "utf-8", "replace"
            )
        except ArchiveError:
            return None

        pages: list[dict[str, Any]] = []
        # Split on OBJECT rather than using an XML parser: these files are large
        # and frequently malformed by 2013-era derivation. But DO preserve LINE
        # and PARAGRAPH structure -- flattening a page to one space-joined string
        # destroys every line-based signal the router depends on, and turns the
        # text into something a model reads far worse.
        for n, chunk in enumerate(re.split(r"(?=<OBJECT)", raw)[1:], start=1):
            head = chunk[:400]
            wm = re.search(r'width="(\d+)"', head)
            hm = re.search(r'height="(\d+)"', head)

            words: list[list[Any]] = []
            confidences: list[int] = []
            para_texts: list[str] = []

            for para in re.split(r"(?=<PARAGRAPH)", chunk)[1:] or [chunk]:
                line_texts: list[str] = []
                for line in re.split(r"(?=<LINE)", para)[1:] or [para]:
                    tokens: list[str] = []
                    for m in re.finditer(
                        r'<WORD coords="(\d+),(\d+),(\d+),(\d+)"'
                        r'(?:\s+x-confidence="(\d+)")?[^>]*>([^<]*)</WORD>',
                        line,
                    ):
                        x0, y0, x1, y1 = (int(m.group(i)) for i in range(1, 5))
                        conf = m.group(5)
                        text = (m.group(6) or "").strip()
                        if not text:
                            continue
                        tokens.append(text)
                        # djvu coords are (left, bottom, right, top) in a
                        # bottom-left origin; normalise to top-left for drawing.
                        words.append([text, x0, y1, x1, y0])
                        if conf is not None:
                            confidences.append(int(conf))
                    if tokens:
                        line_texts.append(" ".join(tokens))
                if line_texts:
                    para_texts.append("\n".join(line_texts))

            if not words:
                continue

            # archive.org's x-confidence runs 0..100 and HIGHER IS BETTER --
            # verified rather than assumed: on a sample document the two
            # cleanest prose pages scored 77.2 and 77.5, the highest on the
            # item, and also had the highest share of common English words.
            #
            # Correlation with a readability proxy was r = 0.42 (n = 16 pages,
            # one document). Real but moderate: treat this as ONE input to
            # reading uncertainty, never as the whole of it, until it has been
            # validated against actual transcription error on the gold set.
            mean_conf = sum(confidences) / len(confidences) if confidences else None
            ocr_conf = None if mean_conf is None else max(0.0, min(1.0, mean_conf / 100.0))

            pages.append(
                {
                    "n": n,
                    "t": "\n\n".join(para_texts),
                    "W": int(wm.group(1)) if wm else None,
                    "H": int(hm.group(1)) if hm else None,
                    "c": None if ocr_conf is None else round(ocr_conf, 4),
                    "w": words,
                }
            )
        if not pages:
            return None
        return {"identifier": identifier, "pages": pages}

    def _fallback_pages(self, identifier: str) -> list[PageText]:
        """No usable XML: return the whole item as one page, honestly labelled.

        A wrong page number is worse than a missing one -- provenance is what
        makes a claim checkable, so we never guess at boundaries.
        """
        text = self.ocr_text(identifier)
        if not text:
            return []
        return [PageText(identifier=identifier, page=1, text=text)]

    # -- page images (the vision / map / figure paths) --------------------

    #: Widest useful render. Measured on a 2621x3751 scan: w1000 returns 309 KB,
    #: w1500 returns 952 KB, and w2000/w3000 return exactly the same bytes as
    #: w1500 -- the service caps there. Asking for more just wastes the
    #: archive's bandwidth for an identical image.
    MAX_PAGE_WIDTH = 1500

    def page_image_url(self, identifier: str, page: int, *, width: int = 1500) -> str:
        """Direct page-image URL, for the vision, figure and map paths.

        `page` is 1-indexed to match `PageText`; the service is 0-indexed.
        Width matters: a 1969 table is unreadable at w500, which is the
        difference between the vision path working and not.
        """
        w = min(int(width), self.MAX_PAGE_WIDTH)
        return f"https://archive.org/download/{identifier}/page/n{page - 1}_w{w}.jpg"

    def page_image(self, identifier: str, page: int, *, width: int = 1500) -> bytes:
        """Page image bytes, cached on disk."""
        w = min(int(width), self.MAX_PAGE_WIDTH)
        path = self.cache / "images" / f"{identifier}_n{page - 1}_w{w}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return path.read_bytes()
        data = _get(self.page_image_url(identifier, page, width=w))
        path.write_bytes(data)
        return data

    def has_page_images(self, identifier: str) -> bool:
        names = [f.get("name", "") for f in self.metadata(identifier).get("files", [])]
        return any(n.endswith(("_jp2.zip", "_jp2.tar")) for n in names) or any(
            n.endswith(".pdf") for n in names
        )

    # -- iteration --------------------------------------------------------

    def iter_items(
        self,
        *,
        title_contains: str | None = None,
        publisher_contains: str | None = None,
        year_range: tuple[int, int] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Filter the index without loading anything over the network."""
        for it in self.load_index():
            if title_contains and title_contains.lower() not in str(it.get("title", "")).lower():
                continue
            if publisher_contains:
                pubs = it.get("publisher") or []
                pubs = pubs if isinstance(pubs, list) else [pubs]
                if not any(publisher_contains.lower() in str(p).lower() for p in pubs):
                    continue
            if year_range:
                raw = it.get("year")
                try:
                    year = int(str(raw)[:4])
                except (TypeError, ValueError):
                    continue
                if not year_range[0] <= year <= year_range[1]:
                    continue
            yield it
