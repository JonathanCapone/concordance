"""Archive identifiers must never become paths outside the configured cache."""

from __future__ import annotations

from pathlib import Path

import pytest

import concordance.archive as archive_module
from concordance.archive import Archive, ArchiveError


UNSAFE_IDENTIFIERS = (
    "",
    ".",
    "..",
    "../outside",
    r"..\outside",
    "safe/../../outside",
    r"safe\..\outside",
    "/absolute/path",
    r"\rooted\path",
    r"\\server\share\item",
    "C:drive-relative",
    r"C:\absolute\item",
    "bad\x00identifier",
    "bad\nidentifier",
    "bad identifier",
    "bad?identifier",
    "bad%2Fidentifier",
    "CON",
    "nul",
    "COM1.report",
    "a" * 101,
    None,
    123,
)


@pytest.mark.parametrize("identifier", UNSAFE_IDENTIFIERS, ids=repr)
def test_every_item_method_rejects_unsafe_identifiers_before_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    identifier: object,
) -> None:
    cache = tmp_path / "cache"
    outside = tmp_path / "outside.json"
    outside.write_bytes(b'{"sentinel": true}')
    archive = Archive(cache)

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("unsafe identifier reached disk or network I/O")

    monkeypatch.setattr(archive_module, "_get", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)

    operations = (
        archive.metadata,
        archive._ocr_filename,
        archive.ocr_text,
        archive._page_cache,
        archive.pages,
        archive._parse_djvu_xml,
        archive._fallback_pages,
        lambda value: archive.page_image_url(value, 1),
        lambda value: archive.page_image(value, 1),
        archive.has_page_images,
    )
    for operation in operations:
        with pytest.raises(ArchiveError, match="unsafe archive identifier"):
            operation(identifier)  # type: ignore[arg-type]

    with outside.open("rb") as fh:
        assert fh.read() == b'{"sentinel": true}'


@pytest.mark.parametrize(
    "identifier",
    ("government-report_1969.01", "A_B.C-D", "123", "a" * 100),
)
def test_real_archive_identifier_characters_are_accepted(
    tmp_path: Path,
    identifier: str,
) -> None:
    archive = Archive(tmp_path / "cache")

    url = archive.page_image_url(identifier, 3, width=1000)

    assert f"/{identifier}/page/n2_w1000.jpg" in url


def test_valid_metadata_is_cached_only_inside_configured_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = Archive(tmp_path / "cache")
    calls: list[str] = []

    def fake_get(url: str, **_kwargs: object) -> bytes:
        calls.append(url)
        return b'{"files": []}'

    monkeypatch.setattr(archive_module, "_get", fake_get)

    assert archive.metadata("gov_report-1969.01") == {"files": []}
    metadata_path = archive.cache / "meta" / "gov_report-1969.01.json"
    assert metadata_path.exists()
    assert metadata_path.resolve().is_relative_to(archive.cache)
    assert archive.index_path().resolve().is_relative_to(archive.cache)
    assert archive._page_cache("gov_report-1969.01").resolve().is_relative_to(archive.cache)
    assert calls == ["https://archive.org/metadata/gov_report-1969.01"]


def test_cache_path_builder_refuses_absolute_and_parent_escapes(tmp_path: Path) -> None:
    archive = Archive(tmp_path / "cache")

    with pytest.raises(ArchiveError, match="escaped"):
        archive._cache_path("meta", "..", "..", "outside.json")
    with pytest.raises(ArchiveError, match="escaped"):
        archive._cache_path(str(tmp_path / "outside.json"))


@pytest.mark.parametrize("collection", ("../other", r"C:\other", "NUL", "bad\nname"))
def test_collection_uses_same_boundary_before_cache_creation(
    tmp_path: Path,
    collection: str,
) -> None:
    cache = tmp_path / "cache"

    with pytest.raises(ArchiveError, match="unsafe archive collection"):
        Archive(cache, collection=collection)

    assert not cache.exists()
