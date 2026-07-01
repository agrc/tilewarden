import json
import sqlite3
from datetime import UTC, datetime

from tilewarden.inventory import SourceObject, build_inventory
from tilewarden.output import write_inventory_outputs


def source_object(name, *, date_created=None, date_last_modified=None):
    return SourceObject(
        name=name,
        date_created=date_created,
        date_last_modified=date_last_modified,
    )


def test_write_inventory_outputs_creates_geopackage_and_summary(tmp_path):
    date_created_0 = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    date_created_1 = datetime(2026, 1, 4, 3, 4, 5, tzinfo=UTC)
    date_last_modified_0 = datetime(2026, 1, 3, 3, 4, 5, tzinfo=UTC)
    date_last_modified_1 = datetime(2026, 1, 5, 3, 4, 5, tzinfo=UTC)
    inventory = build_inventory(
        [
            source_object("Terrain/0/0/0"),
            source_object(
                "Terrain/1/0/0",
                date_created=date_created_0,
                date_last_modified=date_last_modified_0,
            ),
            source_object(
                "Terrain/1/1/1",
                date_created=date_created_1,
                date_last_modified=date_last_modified_1,
            ),
            source_object("Terrain/metadata.json"),
        ],
        layout="auto",
        level_filter=None,
    )

    output_files, summary_path, summary = write_inventory_outputs(
        inventory,
        output_dir=tmp_path,
        bucket="example-bucket",
        prefix="Terrain/",
        layout="auto",
        matrix_set="webmercator",
        levels_option=None,
        processing_time_seconds=1.25,
    )

    assert sorted(output_files) == [0, 1]
    assert output_files[0] == output_files[1]
    assert output_files[1].name == "example-bucket-tile-footprints.gpkg"
    assert summary_path.name == "example-bucket-summary.json"
    assert summary["prefix"] == "Terrain/"
    assert summary["layout"] == "prefix/z/x/y"
    assert summary["total_processing_time_seconds"] == 1.25
    assert summary["skipped_object_count"] == 1
    assert summary["total_tile_count"] == 3

    with sqlite3.connect(output_files[1]) as connection:
        layer_names = [
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM gpkg_contents ORDER BY table_name"
            ).fetchall()
        ]
        feature_count = connection.execute("SELECT COUNT(*) FROM tile_footprints_l01").fetchone()[0]
        properties = connection.execute(
            """
            SELECT bucket, prefix, layout, matrix_set, blob_name, date_created,
                date_last_modified, wkid
            FROM tile_footprints_l01
            ORDER BY row, column
            LIMIT 1
            """
        ).fetchone()
        srs_id = connection.execute(
            "SELECT srs_id FROM gpkg_geometry_columns WHERE table_name = 'tile_footprints_l01'"
        ).fetchone()[0]
        spatial_index_count = connection.execute(
            "SELECT COUNT(*) FROM rtree_tile_footprints_l01_geom"
        ).fetchone()[0]
        geometry = connection.execute("SELECT geom FROM tile_footprints_l01 LIMIT 1").fetchone()[0]

    assert layer_names == ["tile_footprints_l00", "tile_footprints_l01"]
    assert feature_count == 2
    assert properties == (
        "example-bucket",
        "Terrain/",
        "prefix/z/x/y",
        "webmercator",
        "Terrain/1/0/0",
        date_created_0.isoformat(),
        date_last_modified_0.isoformat(),
        3857,
    )
    assert srs_id == 3857
    assert spatial_index_count == 2
    assert geometry.startswith(b"GP")

    written_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert written_summary["generated_file_count"] == 1
    assert written_summary["prefix"] == "Terrain/"
    assert written_summary["layout"] == "prefix/z/x/y"
    assert written_summary["total_processing_time_seconds"] == 1.25
    assert written_summary["generated_files"] == [str(output_files[1])]
    assert written_summary["min_date_created"] == date_created_0.isoformat()
    assert written_summary["max_date_created"] == date_created_1.isoformat()
    assert written_summary["min_date_last_modified"] == date_last_modified_0.isoformat()
    assert written_summary["max_date_last_modified"] == date_last_modified_1.isoformat()
    assert written_summary["levels_summary"][1]["min_column"] == 0
    assert written_summary["levels_summary"][1]["max_row"] == 1
    assert written_summary["levels_summary"][1]["min_date_created"] == date_created_0.isoformat()
    assert written_summary["levels_summary"][1]["max_date_created"] == date_created_1.isoformat()


def test_write_inventory_outputs_sanitizes_bucket_name(tmp_path):
    inventory = build_inventory([source_object("0/0/0")], layout="auto", level_filter=None)

    output_files, summary_path, _summary = write_inventory_outputs(
        inventory,
        output_dir=tmp_path,
        bucket="bucket/name",
        prefix="",
        layout="auto",
        matrix_set="webmercator",
        levels_option="0",
        processing_time_seconds=0.5,
    )

    assert output_files[0].name == "bucket_name-tile-footprints.gpkg"
    assert summary_path.name == "bucket_name-summary.json"
    assert not (tmp_path / "bucket_name-L00-tile-footprints.gpkg").exists()
