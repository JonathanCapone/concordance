"""Build the offline Ontario place index from Natural Resources Canada data.

The CGNDB province archive is refreshed weekly and is intentionally kept out of
Git.  This script reduces its 58,000 features to the populated places and
administrative areas a municipal-document resolver can legitimately select.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import http.client
import io
import json
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CGNDB_DATASET_URL = (
    "https://open.canada.ca/data/en/dataset/"
    "e27c6eba-3c5d-4051-9db2-082dc6411c2c"
)
CGNDB_ONTARIO_URL = (
    "https://ftp.maps.canada.ca/pub/nrcan_rncan/vector/"
    "geobase_cgn_toponyme/prov_csv_eng/cgn_on_csv_eng.zip"
)
OPEN_GOVERNMENT_LICENCE_URL = (
    "https://open.canada.ca/en/open-government-licence-canada"
)
USER_AGENT = "ground-truth/0.1 (CGNDB gazetteer builder)"

ROOT = Path(__file__).resolve().parents[1]
GAZETTEER_DIR = ROOT / "data" / "gazetteer"
CACHE_PATH = GAZETTEER_DIR / "cache" / "cgn_on_csv_eng.zip"
INDEX_PATH = GAZETTEER_DIR / "cgn_on_places.csv"
MANIFEST_PATH = GAZETTEER_DIR / "source.json"

_INCLUDED_CATEGORIES = {"Populated Place", "Administrative Area"}
_SOURCE_CSV_NAME = "cgn_on_csv_eng.csv"
_MANIFEST_SCHEMA_VERSION = 1
_INDEX_FORMAT_VERSION = 1
_MIN_SOURCE_ROWS = 40_000
_MIN_INDEX_ROWS = 8_000
_EXPECTED_HEADER = (
    "CGNDB ID",
    "Geographical Name",
    "ISO Language Code",
    "Language",
    "Syllabic Form",
    "Generic Term",
    "Generic Category",
    "Concise Code",
    "Toponymic Feature ID",
    "Latitude",
    "Longitude",
    "Location",
    "Province - Territory",
    "Relevance at Scale",
    "Decision Date",
    "Source",
)
_OUTPUT_FIELDS = (
    "id",
    "name",
    "generic_term",
    "generic_category",
    "concise_code",
    "lat",
    "lon",
    "location",
    "decision_date",
)


def _download(
    url: str, path: Path, *, retries: int = 4
) -> tuple[Path, dict[str, str | int | None]]:
    """Download to staging; the caller publishes only after source validation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    last: Exception | None = None

    for attempt in range(retries):
        temp_path: Path | None = None
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=180) as response:
                with tempfile.NamedTemporaryFile(
                    dir=path.parent, prefix=f".{path.name}.", delete=False
                ) as temporary:
                    shutil.copyfileobj(response, temporary)
                    temp_path = Path(temporary.name)
                raw_length = response.headers.get("Content-Length")
                expected_length = (
                    int(raw_length) if raw_length and raw_length.isdigit() else None
                )
                if expected_length is not None and temp_path.stat().st_size != expected_length:
                    raise RuntimeError(
                        f"incomplete download: expected {expected_length} bytes, "
                        f"received {temp_path.stat().st_size}"
                    )
                return (
                    temp_path,
                    {
                        "http_status": getattr(response, "status", None),
                        "last_modified": response.headers.get("Last-Modified"),
                        "etag": response.headers.get("ETag"),
                        "content_type": response.headers.get("Content-Type"),
                        "content_length": expected_length,
                        "retrieved_at": datetime.now(timezone.utc).isoformat(
                            timespec="seconds"
                        ),
                    },
                )
        except (
            OSError,
            RuntimeError,
            http.client.HTTPException,
            urllib.error.URLError,
            urllib.error.HTTPError,
        ) as exc:
            last = exc
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            if attempt + 1 < retries:
                time.sleep(2**attempt)

    raise RuntimeError(f"failed after {retries} attempts: {url} ({last})")


def _source_rows(archive: Path) -> Iterator[dict[str, str]]:
    with zipfile.ZipFile(archive) as bundle:
        members = [item.filename for item in bundle.infolist() if not item.is_dir()]
        if members != [_SOURCE_CSV_NAME]:
            raise RuntimeError(f"unexpected CGNDB archive layout: {members!r}")
        with bundle.open(members[0]) as raw:
            with io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
                reader = csv.DictReader(text)
                if tuple(reader.fieldnames or ()) != _EXPECTED_HEADER:
                    raise RuntimeError(
                        "CGNDB CSV schema changed; review the build before publishing "
                        f"a new index (received {reader.fieldnames!r})"
                    )
                yield from reader


def _compact(row: dict[str, str]) -> dict[str, str]:
    return {
        "id": row["CGNDB ID"],
        "name": row["Geographical Name"],
        "generic_term": row["Generic Term"],
        "generic_category": row["Generic Category"],
        "concise_code": row["Concise Code"],
        "lat": row["Latitude"],
        "lon": row["Longitude"],
        "location": row["Location"],
        "decision_date": row["Decision Date"],
    }


def _write_index(archive: Path, output: Path) -> tuple[int, int]:
    source_count = 0
    kept: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    seen_categories: set[str] = set()
    for row in _source_rows(archive):
        source_count += 1
        if None in row or any(value is None for value in row.values()):
            raise RuntimeError(f"malformed CGNDB CSV row {source_count}")

        identifier = row["CGNDB ID"]
        if not re.fullmatch(r"[A-Z]{5}", identifier):
            raise RuntimeError(f"invalid CGNDB ID on row {source_count}: {identifier!r}")
        if identifier in seen_ids:
            raise RuntimeError(f"duplicate CGNDB ID on row {source_count}: {identifier}")
        seen_ids.add(identifier)

        if row["Province - Territory"] != "Ontario":
            raise RuntimeError(
                f"non-Ontario row in Ontario archive: {row['Province - Territory']!r}"
            )
        if not row["Geographical Name"].strip():
            raise RuntimeError(f"blank geographical name on row {source_count}")
        try:
            lat = float(row["Latitude"])
            lon = float(row["Longitude"])
        except ValueError as exc:
            raise RuntimeError(f"invalid coordinate on row {source_count}") from exc
        if not (41.5 <= lat <= 57.0 and -95.5 <= lon <= -74.0):
            raise RuntimeError(
                f"coordinate outside Ontario bounds on row {source_count}: {lat}, {lon}"
            )

        category = row["Generic Category"]
        seen_categories.add(category)
        if category in _INCLUDED_CATEGORIES:
            kept.append(_compact(row))

    if source_count < _MIN_SOURCE_ROWS or len(kept) < _MIN_INDEX_ROWS:
        raise RuntimeError(
            "CGNDB source is unexpectedly small: "
            f"{source_count} source rows, {len(kept)} retained"
        )
    missing_categories = _INCLUDED_CATEGORIES - seen_categories
    if missing_categories:
        raise RuntimeError(f"CGNDB source lacks categories: {sorted(missing_categories)}")

    # The five-letter source ID is stable across supported Python/Unicode
    # versions; locale-like name sorting is not.
    kept.sort(key=lambda row: row["id"])
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            dir=output.parent,
            prefix=f".{output.name}.",
            encoding="utf-8",
            newline="",
            delete=False,
        ) as temporary:
            writer = csv.DictWriter(
                temporary, fieldnames=_OUTPUT_FIELDS, lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(kept)
            temp_path = Path(temporary.name)
        os.replace(temp_path, output)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return source_count, len(kept)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _previous_manifest() -> dict[str, Any]:
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_manifest(manifest: dict[str, Any], output: Path) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            dir=output.parent,
            prefix=f".{output.name}.",
            encoding="utf-8",
            newline="",
            delete=False,
        ) as temporary:
            json.dump(manifest, temporary, indent=2, ensure_ascii=False)
            temporary.write("\n")
            temp_path = Path(temporary.name)
        os.replace(temp_path, output)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _check_count_change(current: int, previous: Any, label: str) -> None:
    if isinstance(previous, int) and current < previous * 0.8:
        raise RuntimeError(
            f"{label} shrank from {previous} to {current}; manual review required"
        )


def _publish_snapshot(
    *,
    archive: Path,
    staged_index: Path,
    staged_manifest: Path,
    downloaded: bool,
    stage: Path,
) -> None:
    """Publish one verified generation or restore every previous artifact."""
    targets = [INDEX_PATH, MANIFEST_PATH]
    if downloaded:
        targets.insert(0, CACHE_PATH)

    backups: dict[Path, Path] = {}
    for target in targets:
        if target.exists():
            backup = stage / f"rollback-{target.name}"
            shutil.copy2(target, backup)
            backups[target] = backup

    published: list[Path] = []
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        if downloaded:
            os.replace(archive, CACHE_PATH)
            published.append(CACHE_PATH)
        os.replace(staged_index, INDEX_PATH)
        published.append(INDEX_PATH)
        # The manifest remains the commit marker and is deliberately last.
        os.replace(staged_manifest, MANIFEST_PATH)
        published.append(MANIFEST_PATH)
    except Exception as exc:
        rollback_errors: list[str] = []
        for target in reversed(published):
            try:
                backup = backups.get(target)
                if backup is None:
                    target.unlink(missing_ok=True)
                else:
                    os.replace(backup, target)
            except OSError as rollback_exc:
                rollback_errors.append(f"{target}: {rollback_exc}")
        if rollback_errors:
            raise RuntimeError(
                "gazetteer publication failed and rollback was incomplete: "
                + "; ".join(rollback_errors)
            ) from exc
        raise RuntimeError(
            "gazetteer publication failed; the previous snapshot was restored"
        ) from exc


@contextlib.contextmanager
def _build_lock() -> Iterator[None]:
    lock = GAZETTEER_DIR / ".build.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(
            f"another gazetteer build may be running ({lock}); "
            "remove a stale lock only after confirming no build is active"
        ) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.write(f"pid={os.getpid()}\n")
        yield
    finally:
        lock.unlink(missing_ok=True)


def build(*, refresh: bool = False) -> dict[str, Any]:
    GAZETTEER_DIR.mkdir(parents=True, exist_ok=True)
    with _build_lock():
        previous = _previous_manifest()
        response: dict[str, str | int | None] = {}

        with tempfile.TemporaryDirectory(
            dir=GAZETTEER_DIR, prefix=".build."
        ) as stage_name:
            stage = Path(stage_name)
            if refresh or not CACHE_PATH.exists():
                archive, response = _download(
                    CGNDB_ONTARIO_URL, stage / CACHE_PATH.name
                )
                downloaded = True
            else:
                archive = CACHE_PATH
                downloaded = False
                archive_sha256 = _sha256(archive)
                if previous.get("archive_sha256") != archive_sha256:
                    raise RuntimeError(
                        "cached CGNDB archive does not match source.json; "
                        "refusing to relabel unverified bytes (run with --refresh)"
                    )
                response = {
                    key: previous.get(key)
                    for key in (
                        "http_status",
                        "last_modified",
                        "etag",
                        "content_type",
                        "content_length",
                        "retrieved_at",
                    )
                }

            staged_index = stage / INDEX_PATH.name
            source_rows, index_rows = _write_index(archive, staged_index)
            _check_count_change(source_rows, previous.get("source_rows"), "source rows")
            _check_count_change(index_rows, previous.get("index_rows"), "index rows")

            archive_sha256 = _sha256(archive)
            index_sha256 = _sha256(staged_index)
            unchanged = (
                previous.get("archive_sha256") == archive_sha256
                and previous.get("index_sha256") == index_sha256
            )
            built_at = (
                previous.get("built_at")
                if unchanged and previous.get("built_at")
                else datetime.now(timezone.utc).isoformat(timespec="seconds")
            )
            manifest: dict[str, Any] = {
                "manifest_schema_version": _MANIFEST_SCHEMA_VERSION,
                "index_format_version": _INDEX_FORMAT_VERSION,
                "dataset": "Canadian Geographical Names - CGN",
                "publisher": "Natural Resources Canada",
                "dataset_url": CGNDB_DATASET_URL,
                "download_url": CGNDB_ONTARIO_URL,
                "licence": "Open Government Licence - Canada",
                "licence_url": OPEN_GOVERNMENT_LICENCE_URL,
                "source_member": _SOURCE_CSV_NAME,
                "built_at": built_at,
                "archive_bytes": archive.stat().st_size,
                "archive_sha256": archive_sha256,
                "source_rows": source_rows,
                "index_path": INDEX_PATH.name,
                "index_bytes": staged_index.stat().st_size,
                "index_sha256": index_sha256,
                "index_rows": index_rows,
                "included_categories": sorted(_INCLUDED_CATEGORIES),
                **response,
            }
            staged_manifest = stage / MANIFEST_PATH.name
            _write_manifest(manifest, staged_manifest)

            _publish_snapshot(
                archive=archive,
                staged_index=staged_index,
                staged_manifest=staged_manifest,
                downloaded=downloaded,
                stage=stage,
            )
            return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh", action="store_true", help="download even when a cache exists"
    )
    args = parser.parse_args()
    print(json.dumps(build(refresh=args.refresh), indent=2))


if __name__ == "__main__":
    main()
