"""Page evidence must come from real archive page boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest

import concordance.archive as archive_module
from concordance.archive import Archive


def test_unpaginated_ocr_cannot_become_page_one_evidence(tmp_path: Path) -> None:
    archive = Archive(tmp_path / "cache")
    identifier = "unpaginated-report"
    full_text = "FIRST PHYSICAL PAGE\nSECOND PHYSICAL PAGE"
    text_path = archive.cache / "text" / f"{identifier}.txt"
    text_path.write_text(full_text, encoding="utf-8")

    assert archive.ocr_text(identifier) == full_text
    assert archive._fallback_pages(identifier) == []


def test_pages_abstain_when_djvu_xml_has_no_usable_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = Archive(tmp_path / "cache")
    identifier = "malformed-report"
    text_path = archive.cache / "text" / f"{identifier}.txt"
    text_path.write_text("OCR exists, but its page boundaries do not.", encoding="utf-8")
    monkeypatch.setattr(archive, "_parse_djvu_xml", lambda _identifier: None)

    assert archive.pages(identifier) == []
    assert archive.ocr_text(identifier) == "OCR exists, but its page boundaries do not."


def test_valid_djvu_page_boundaries_still_produce_evidence_pages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = Archive(tmp_path / "cache")
    identifier = "paginated-report"
    xml = b"""<DjVuXML><BODY>
<OBJECT width="1000" height="2000"><PAGE><PARAGRAPH><LINE>
<WORD coords="10,1900,100,1950" x-confidence="90">First</WORD>
<WORD coords="110,1900,200,1950" x-confidence="80">page</WORD>
</LINE></PARAGRAPH></PAGE></OBJECT>
<OBJECT width="1200" height="2200"><PAGE><PARAGRAPH><LINE>
<WORD coords="20,2000,120,2050" x-confidence="95">Second</WORD>
<WORD coords="130,2000,230,2050" x-confidence="85">page</WORD>
</LINE></PARAGRAPH></PAGE></OBJECT>
</BODY></DjVuXML>"""

    monkeypatch.setattr(
        archive,
        "metadata",
        lambda _identifier: {"files": [{"name": f"{identifier}_djvu.xml"}]},
    )
    monkeypatch.setattr(archive_module, "_get", lambda *_args, **_kwargs: xml)

    pages = archive.pages(identifier, with_words=True)

    assert [page.page for page in pages] == [1, 2]
    assert [page.text for page in pages] == ["First page", "Second page"]
    assert [(page.width, page.height) for page in pages] == [(1000, 2000), (1200, 2200)]
    assert [[word.text for word in page.words] for page in pages] == [
        ["First", "page"],
        ["Second", "page"],
    ]
