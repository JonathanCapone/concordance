"""Build the offline Ontario place index from Natural Resources Canada data.

The CGNDB province archive is refreshed weekly and is intentionally kept out of
Git.  This script reduces its 58,000 features to the populated places and
administrative areas a municipal-document resolver can legitimately select.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
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


def _download(url: str, path: Path, *, retries: int = 4) -> dict[str, str | int | None]:
    """Download atomically; an interrupted weekly refresh must not poison the cache."""
    path.parent.mkdir(parents=True, exist_ok=True)
    last: Exception | None = None

    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=180) as response:
                with tempfile.NamedTemporaryFile(
                    dir=path.parent, prefix=f".{path.name}.", delete=False
                ) as temporary:
                    shutil.copyfileobj(response, temporary)
                    temp_path = Path(temporary.name)
                os.replace(temp_path, path)
                return {
                    "http_status": getattr(response, "status", None),
                    "last_modified": response.headers.get("Last-Modified"),
                    "content_type": response.headers.get("Content-Type"),
                }
        except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
            last = exc
            time.sleep(2**attempt)

    raise RuntimeError(f"failed after {retries} attempts: {url} ({last})")


def _source_rows(archive: Path) -> Iterator[dict[str, str]]:
    with zipfile.ZipFile(archive) as bundle:
        csv_names = [name for name in bundle.namelist() if name.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise RuntimeError(
                f"expected one CSV in {archive.name}, found {len(csv_names)}"
            )
        with bundle.open(csv_names[0]) as raw:
            with io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
                yield from csv.DictReader(text)


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
    for row in _source_rows(archive):
        source_count += 1
        if row.get("Generic Category") in _INCLUDED_CATEGORIES:
            kept.append(_compact(row))

    kept.sort(
        key=lambda row: (
            row["name"].casefold(),
            row["generic_category"],
            row["generic_term"],
            row["id"],
        )
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        dir=output.parent,
        prefix=f".{output.name}.",
        encoding="utf-8",
        newline="",
        delete=False,
    ) as temporary:
        writer = csv.DictWriter(temporary, fieldnames=_OUTPUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(kept)
        temp_path = Path(temporary.name)
    os.replace(temp_path, output)
    return source_count, len(kept)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build(*, refresh: bool = False) -> dict[str, Any]:
    GAZETTEER_DIR.mkdir(parents=True, exist_ok=True)
    response: dict[str, str | int | None] = {}
    if refresh or not CACHE_PATH.exists():
        response = _download(CGNDB_ONTARIO_URL, CACHE_PATH)

    source_rows, index_rows = _write_index(CACHE_PATH, INDEX_PATH)
    manifest: dict[str, Any] = {
        "dataset": "Canadian Geographical Names - CGN",
        "publisher": "Natural Resources Canada",
        "dataset_url": CGNDB_DATASET_URL,
        "download_url": CGNDB_ONTARIO_URL,
        "licence": "Open Government Licence - Canada",
        "licence_url": OPEN_GOVERNMENT_LICENCE_URL,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "archive_bytes": CACHE_PATH.stat().st_size,
        "archive_sha256": _sha256(CACHE_PATH),
        "source_rows": source_rows,
        "index_rows": index_rows,
        "included_categories": sorted(_INCLUDED_CATEGORIES),
        **response,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
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
