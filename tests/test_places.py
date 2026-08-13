import io
import json
from pathlib import Path
import zipfile

import pytest

from concordance.places import Place, resolve
from scripts import build_gazetteer as builder


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("raw", ["Sault Ste Marie", "Sault Ste. Marie"])
def test_sault_spelling_variants_resolve_to_one_city(raw):
    place = resolve(raw, 1964)

    assert place is not None
    assert place.canonical == "Sault Ste. Marie"
    assert place.kind == "city"
    assert (place.lat, place.lon) == pytest.approx((46.558889, -84.346944))


@pytest.mark.parametrize(
    "raw",
    [
        "Sidney Township (Batawa)",
        "Sidney (Batawa)",
        "Sidney Twp.- (Batawa)",
    ],
)
def test_sidney_batawa_variants_keep_township_and_locality(raw):
    place = resolve(raw, 1970)

    assert place is not None
    assert place.canonical == "Sidney Township (Batawa)"
    assert place.kind == "township"
    assert (place.lat, place.lon) == pytest.approx((44.1722222, -77.5961111))


@pytest.mark.parametrize(
    "raw", ["Moore Township (Corunna)", "Moore Twp. - Corunna"]
)
def test_moore_corunna_variants_keep_township_and_locality(raw):
    place = resolve(raw, 1970)

    assert place is not None
    assert place.canonical == "Moore Township (Corunna)"
    assert place.kind == "township"
    assert (place.lat, place.lon) == pytest.approx((42.8855556, -82.4483333))


def test_woolwich_sites_share_a_township_without_losing_the_locality():
    township = resolve("Woolwich Twp", 1973)
    elmira = resolve("Woolwich Twp., Elmira", 1974)
    st_jacobs = resolve("Woolwich Twp., St. Jacobs", 1974)

    assert township is not None and elmira is not None and st_jacobs is not None
    assert township.canonical == "Woolwich Township"
    assert elmira.canonical == "Woolwich Township (Elmira)"
    assert st_jacobs.canonical == "Woolwich Township (St. Jacobs)"
    assert {township.kind, elmira.kind, st_jacobs.kind} == {"township"}
    assert (elmira.lat, elmira.lon) != (st_jacobs.lat, st_jacobs.lon)


@pytest.mark.parametrize(
    ("raw", "year"),
    [
        ("Burlington Drury Lane", 1961),
        ("Burlington Elizabeth Gardens", 1962),
        ("Burlington Skyway", 1964),
    ],
)
def test_burlington_sites_use_the_report_era_municipal_class(raw, year):
    historical = resolve(raw, year)
    later = resolve(raw, 1974)

    assert historical is not None and later is not None
    assert historical.kind == "town"
    assert later.kind == "city"
    assert historical.canonical == later.canonical
    if raw == "Burlington Elizabeth Gardens":
        assert "Elizabeth Gardens" in historical.note
        assert "Burlington reference point" not in historical.note


def test_port_colborne_changes_from_town_to_city_in_1966():
    town = resolve("Port Colborne", 1964)
    city = resolve("Port Colborne", 1966)

    assert town is not None and city is not None
    assert town.kind == "town"
    assert city.kind == "city"


def test_moosonee_is_not_backcast_as_a_town_before_2001():
    board_era = resolve("Moosonee Water Supply System And", 1972)
    town_era = resolve("Moosonee", 2001)

    assert board_era is not None and town_era is not None
    assert board_era.kind == "unknown"
    assert town_era.kind == "town"
    assert "Development Area Board" in board_era.note


def test_misleading_longlac_twp_label_uses_the_1974_legal_class():
    place = resolve("Twp Of Longlac", 1974)

    assert place is not None
    assert place.canonical == "Longlac"
    assert place.kind == "town"
    assert place.confidence >= 0.75
    assert "label says Twp" in place.note


def test_kingston_city_and_township_are_different_places():
    city = resolve("Kingston", 1970)
    township = resolve("Kingston Twp", 1971)

    assert city is not None and township is not None
    assert city.canonical == "Kingston"
    assert township.canonical == "Kingston Township"
    assert city.kind == "city"
    assert township.kind == "township"
    assert (city.lat, city.lon) != (township.lat, township.lon)


def test_westminster_and_westminster_township_are_not_conflated():
    locality = resolve("Westminster", 1970)
    township = resolve("Westminster Twp", 1971)

    assert locality is not None and township is not None
    assert locality.canonical == "Westminster"
    assert township.canonical == "Westminster Township"
    assert (locality.lat, locality.lon) != (township.lat, township.lon)
    assert locality.lon == pytest.approx(-81.18878)


@pytest.mark.parametrize(
    "raw",
    [
        "Operating Cost Summary",
        "Ontario Water Resources Commission",
        "Thirty Seven Municipal",
        "Evaluation Of The Village Of Grand Valley",
    ],
)
def test_non_places_are_rejected(raw):
    assert resolve(raw, 1970) is None


def test_fort_william_resolution_explains_both_sides_of_amalgamation():
    historical = resolve("Fort William", 1965)
    too_late = resolve("Fort William", 1990)

    assert historical is not None and too_late is not None
    assert historical.canonical == too_late.canonical == "Fort William"
    assert historical.superseded_by == too_late.superseded_by == "Thunder Bay"
    assert historical.as_of_year == 1965
    assert too_late.as_of_year == 1990
    assert "separate city in 1965" in historical.note
    assert "no longer existed" in too_late.note
    assert historical.confidence > too_late.confidence


def test_thunder_bay_itself_is_era_aware():
    too_early = resolve("Thunder Bay", 1965)
    valid = resolve("Thunder Bay", 1971)

    assert too_early is not None and valid is not None
    assert "did not exist" in too_early.note
    assert "was valid" in valid.note
    assert too_early.confidence < valid.confidence


def test_nepean_changes_from_township_to_city_before_ottawa_amalgamation():
    township = resolve("Nepean", 1964)
    city = resolve("Nepean", 1990)

    assert township is not None and city is not None
    assert township.kind == "township"
    assert city.kind == "city"
    assert township.superseded_by == city.superseded_by == "Ottawa"


def test_markham_uses_the_report_era_municipal_class():
    village = resolve("Markham", 1968)
    town = resolve("Markham", 1969)
    city = resolve("Markham", 2013)

    assert village is not None and town is not None and city is not None
    assert (village.kind, town.kind, city.kind) == ("village", "town", "city")


def test_timmins_changes_from_town_to_city_at_the_1973_amalgamation():
    town = resolve("Timmins", 1965)
    city = resolve("Timmins", 1974)

    assert town is not None and city is not None
    assert town.kind == "town"
    assert city.kind == "city"


def test_meaford_uses_the_historical_urban_point_not_the_2001_municipal_point():
    historical = resolve("Meaford", 1972)
    current = resolve("Meaford", 2010)

    assert historical is not None and current is not None
    assert historical.kind == current.kind == "town"
    assert (historical.lat, historical.lon) == pytest.approx(
        (44.601389, -80.599444)
    )
    assert (historical.lat, historical.lon) != (current.lat, current.lon)
    assert historical.superseded_by == "Municipality of Meaford"
    assert current.superseded_by is None


def test_sudbury_and_ear_falls_keep_their_fabric_era_municipal_classes():
    sudbury = resolve("Sudbury", 1973)
    ear_falls = resolve("Ear Falls", 1974)

    assert sudbury is not None and ear_falls is not None
    assert sudbury.kind == "city"
    assert ear_falls.kind == "township"


@pytest.mark.parametrize(
    ("name", "year", "kind"),
    [
        ("Alfred", 1963, "village"),
        ("Trenton", 1964, "town"),
        ("Fergus", 1964, "town"),
        ("Paris", 1965, "town"),
        ("Chatham", 1966, "city"),
        ("Cayuga", 1971, "village"),
        ("Cayuga", 1974, "unknown"),
    ],
)
def test_source_reports_control_historical_municipal_class(name, year, kind):
    place = resolve(name, year)

    assert place is not None
    assert place.kind == kind


def test_qualified_cgndb_town_term_maps_to_town():
    place = resolve("St. Marys", 1973)

    assert place is not None
    assert place.kind == "town"


@pytest.mark.parametrize("locality", ["Galt", "Preston", "Hespeler"])
def test_cambridge_parenthetical_forms_preserve_the_predecessor_locality(locality):
    place = resolve(f"Cambridge ({locality})", 1974)

    assert place is not None
    assert place.canonical == locality
    assert place.superseded_by == "Cambridge"
    assert locality in place.note


@pytest.mark.parametrize(
    ("first", "second", "canonical"),
    [
        (
            "Haileybury Water Treatment Plant And",
            "Haileybury : Water Treatment Plant And",
            "Haileybury",
        ),
        (
            "Red Lake Twp. Water Treatment Plant And",
            "Red Lake Twp, Water Treatment Plant And",
            "Red Lake Township",
        ),
        (
            "Newmarket-E. Gwillimbury",
            "Newmarket-East Gwillimbury",
            "Newmarket-East Gwillimbury",
        ),
    ],
)
def test_corpus_formatting_variants_have_one_canonical_name(first, second, canonical):
    a = resolve(first)
    b = resolve(second)

    assert a is not None and b is not None
    assert a.canonical == b.canonical == canonical
    assert (a.lat, a.lon) == (b.lat, b.lon)


def test_joint_service_area_stays_visible_as_ambiguous():
    place = resolve("Newmarket-East Gwillimbury", 1969)

    assert place is not None
    assert place.lat is None and place.lon is None
    assert place.confidence < 0.75
    assert "Joint municipal" in place.note


@pytest.mark.parametrize("raw", ["Newmarket Area", "North Bay Area"])
def test_multi_municipality_area_labels_do_not_invent_a_point(raw):
    place = resolve(raw, 1965)

    assert place is not None
    assert place.lat is None and place.lon is None
    assert place.confidence < 0.75
    assert "service-area" in place.note


def test_county_context_disambiguates_the_town_of_simcoe():
    place = resolve("Simcoe, County Of Norfolk : Municipal", 1964)

    assert place is not None
    assert place.canonical == "Simcoe"
    assert place.kind == "town"
    assert (place.lat, place.lon) == pytest.approx((42.84186, -80.31405))


def test_historical_alias_keeps_the_canonical_era_state():
    before = resolve("Halton Hills, Georgetown", 1965)
    after = resolve("Halton Hills, Georgetown", 1974)

    assert before is not None and after is not None
    assert before.canonical == after.canonical == "Georgetown"
    assert "separate town in 1965" in before.note
    assert "no longer existed" in after.note
    assert after.confidence < before.confidence


def test_unknown_name_is_not_fuzzy_matched():
    assert resolve("Brooklyn", 1963) is None
    assert resolve("Sidneyland", 1965) is None


def test_at_least_eighty_percent_of_fabric_has_plausible_coordinates():
    fabric = json.loads((ROOT / "data" / "fabric.json").read_text(encoding="utf-8"))
    resolved: list[Place] = []

    for municipality in fabric["municipalities"]:
        place = resolve(municipality["name"], min(municipality["years"]))
        if place is not None and place.lat is not None and place.lon is not None:
            assert 41.5 <= place.lat <= 57.0
            assert -95.5 <= place.lon <= -74.0
            resolved.append(place)

    assert len(resolved) / len(fabric["municipalities"]) >= 0.8


def test_every_curated_amalgamation_has_a_source():
    payload = json.loads(
        (ROOT / "data" / "gazetteer" / "amalgamations.json").read_text(
            encoding="utf-8"
        )
    )

    assert payload["entries"]
    for entry in payload["entries"]:
        assert entry["sources"]
        assert all(source["url"].startswith("https://") for source in entry["sources"])


def _archive(member: str, body: bytes) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as bundle:
        bundle.writestr(member, body)
    return output.getvalue()


_SHORT_SOURCE = (
    ",".join(builder._EXPECTED_HEADER)
    + "\r\n"
    + ",".join(
        [
            "ABCDE",
            "Example",
            "eng",
            "English",
            "",
            "Town",
            "Populated Place",
            "TOWN",
            "1",
            "45.0",
            "-80.0",
            "Example County",
            "Ontario",
            "",
            "2000-01-01",
            "CGNDB",
        ]
    )
    + "\r\n"
).encode("utf-8")


@pytest.mark.parametrize(
    "payload",
    [
        b"<html>temporary upstream error</html>",
        _archive("unexpected.csv", b"not the Ontario export"),
        _archive("cgn_on_csv_eng.csv", b"wrong,header\r\n"),
        _archive("cgn_on_csv_eng.csv", _SHORT_SOURCE),
    ],
    ids=["html", "wrong-member", "wrong-header", "suspiciously-short"],
)
def test_failed_refresh_preserves_the_last_verified_snapshot(
    tmp_path, monkeypatch, payload
):
    gazetteer = tmp_path / "gazetteer"
    cache = gazetteer / "cache" / "cgn_on_csv_eng.zip"
    index = gazetteer / "cgn_on_places.csv"
    manifest = gazetteer / "source.json"
    cache.parent.mkdir(parents=True)
    old_manifest = b'{"archive_sha256": "last-known-good"}\n'
    cache.write_bytes(b"last-known-good archive")
    index.write_bytes(b"last-known-good index")
    manifest.write_bytes(old_manifest)

    monkeypatch.setattr(builder, "GAZETTEER_DIR", gazetteer)
    monkeypatch.setattr(builder, "CACHE_PATH", cache)
    monkeypatch.setattr(builder, "INDEX_PATH", index)
    monkeypatch.setattr(builder, "MANIFEST_PATH", manifest)

    def fake_download(url, path):
        path.write_bytes(payload)
        return path, {"retrieved_at": "2026-01-01T00:00:00+00:00"}

    monkeypatch.setattr(builder, "_download", fake_download)

    with pytest.raises((RuntimeError, zipfile.BadZipFile)):
        builder.build(refresh=True)

    assert cache.read_bytes() == b"last-known-good archive"
    assert index.read_bytes() == b"last-known-good index"
    assert manifest.read_bytes() == old_manifest
    assert not (gazetteer / ".build.lock").exists()
    assert not list(gazetteer.glob(".build.*"))


def test_unverified_cache_is_rejected_before_it_can_build_an_index(
    tmp_path, monkeypatch
):
    gazetteer = tmp_path / "gazetteer"
    cache = gazetteer / "cache" / "cgn_on_csv_eng.zip"
    index = gazetteer / "cgn_on_places.csv"
    manifest = gazetteer / "source.json"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"locally modified but plausibly shaped archive")
    index.write_bytes(b"last-known-good index")
    old_manifest = b'{"archive_sha256": "different-hash"}\n'
    manifest.write_bytes(old_manifest)

    monkeypatch.setattr(builder, "GAZETTEER_DIR", gazetteer)
    monkeypatch.setattr(builder, "CACHE_PATH", cache)
    monkeypatch.setattr(builder, "INDEX_PATH", index)
    monkeypatch.setattr(builder, "MANIFEST_PATH", manifest)

    def must_not_build(*args, **kwargs):
        pytest.fail("unverified cache reached the index builder")

    monkeypatch.setattr(builder, "_write_index", must_not_build)

    with pytest.raises(RuntimeError, match="does not match source.json"):
        builder.build(refresh=False)

    assert index.read_bytes() == b"last-known-good index"
    assert manifest.read_bytes() == old_manifest
    assert not (gazetteer / ".build.lock").exists()


def test_manifest_publish_failure_rolls_back_cache_and_index(tmp_path, monkeypatch):
    gazetteer = tmp_path / "gazetteer"
    cache = gazetteer / "cache" / "cgn_on_csv_eng.zip"
    index = gazetteer / "cgn_on_places.csv"
    manifest = gazetteer / "source.json"
    cache.parent.mkdir(parents=True)
    old_cache = b"last-known-good archive"
    old_index = b"last-known-good index"
    old_manifest = b'{"archive_sha256": "last-known-good"}\n'
    cache.write_bytes(old_cache)
    index.write_bytes(old_index)
    manifest.write_bytes(old_manifest)

    monkeypatch.setattr(builder, "GAZETTEER_DIR", gazetteer)
    monkeypatch.setattr(builder, "CACHE_PATH", cache)
    monkeypatch.setattr(builder, "INDEX_PATH", index)
    monkeypatch.setattr(builder, "MANIFEST_PATH", manifest)

    def fake_download(url, path):
        path.write_bytes(b"verified new archive")
        return path, {"retrieved_at": "2026-01-01T00:00:00+00:00"}

    def fake_write_index(archive, output):
        output.write_bytes(b"verified new index")
        return 50_000, 9_000

    monkeypatch.setattr(builder, "_download", fake_download)
    monkeypatch.setattr(builder, "_write_index", fake_write_index)
    real_replace = builder.os.replace

    def fail_final_manifest(source, destination):
        if Path(destination) == manifest:
            raise OSError("injected manifest publication failure")
        real_replace(source, destination)

    monkeypatch.setattr(builder.os, "replace", fail_final_manifest)

    with pytest.raises(RuntimeError, match="previous snapshot was restored"):
        builder.build(refresh=True)

    assert cache.read_bytes() == old_cache
    assert index.read_bytes() == old_index
    assert manifest.read_bytes() == old_manifest
    assert not (gazetteer / ".build.lock").exists()
    assert not list(gazetteer.glob(".build.*"))
