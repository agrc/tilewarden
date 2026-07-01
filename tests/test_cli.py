import json
import sqlite3
import sys
import types
from datetime import UTC, datetime
from io import StringIO

import pytest

from tilewarden import cli
from tilewarden.inventory import SourceObject


def source_object(name, *, date_created=None, date_last_modified=None):
    return SourceObject(
        name=name,
        date_created=date_created,
        date_last_modified=date_last_modified,
    )


def test_inventory_cli_writes_outputs_and_prints_summary(monkeypatch, tmp_path, capsys):
    date_created = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    date_last_modified = datetime(2026, 1, 3, 3, 4, 5, tzinfo=UTC)

    def fake_list_source_objects(*, bucket_name, prefix, project):
        assert bucket_name == "tiles"
        assert prefix == "Terrain/"
        assert project == "proj"
        return [
            source_object("Terrain/0/0/0"),
            source_object(
                "Terrain/1/0/0",
                date_created=date_created,
                date_last_modified=date_last_modified,
            ),
            source_object("Terrain/1/1/1"),
            source_object("Terrain/readme.txt"),
        ]

    monkeypatch.setattr(cli, "list_source_objects", fake_list_source_objects)

    exit_code = cli.main(
        [
            "inventory",
            "tiles",
            "--output",
            str(tmp_path),
            "--prefix",
            "Terrain/",
            "--project",
            "proj",
        ]
    )

    captured = capsys.readouterr()
    summary_path = tmp_path / "tiles-summary.json"
    geopackage_path = tmp_path / "tiles-tile-footprints.gpkg"

    assert exit_code == 0
    assert summary_path.exists()
    assert geopackage_path.exists()
    assert not (tmp_path / "tiles-L01-tile-footprints.gpkg").exists()
    assert "Bucket: tiles" in captured.out
    assert "Prefix: Terrain/" in captured.out
    assert "Layout: prefix/z/x/y" in captured.out
    assert "Skipped object count: 1" in captured.out
    assert "Total tile count: 3" in captured.out
    assert "Generated file count: 1" in captured.out
    assert "Level  Tiles  Created     Last modified" in captured.out
    assert "Output file" not in captured.out
    assert "2026-01-02" in captured.out
    assert "2026-01-03" in captured.out
    assert date_created.isoformat() not in captured.out
    assert date_last_modified.isoformat() not in captured.out
    assert "Columns" not in captured.out
    assert "Rows" not in captured.out
    assert str(summary_path) in captured.out
    assert captured.err == ""

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["generated_file_count"] == 1
    assert summary["prefix"] == "Terrain/"
    assert summary["layout"] == "prefix/z/x/y"
    assert summary["min_date_created"] == date_created.isoformat()
    assert summary["max_date_last_modified"] == date_last_modified.isoformat()
    assert [level["level"] for level in summary["levels_summary"]] == [0, 1]

    with sqlite3.connect(geopackage_path) as connection:
        source_dates = connection.execute(
            """
            SELECT date_created, date_last_modified
            FROM tile_footprints_l01
            WHERE blob_name = 'Terrain/1/0/0'
            """
        ).fetchone()

    assert source_dates == (date_created.isoformat(), date_last_modified.isoformat())


def test_print_summary_formats_tile_counts_with_commas(tmp_path):
    date_created = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    date_last_modified = datetime(2026, 1, 3, 3, 4, 5, tzinfo=UTC)
    inventory = cli.build_inventory(
        [
            source_object(
                f"11/{column}/0",
                date_created=date_created,
                date_last_modified=date_last_modified,
            )
            for column in range(1234)
        ],
        layout="auto",
        level_filter=None,
    )
    stdout = StringIO()

    cli.print_summary(
        inventory=inventory,
        stats=inventory.level_stats(),
        bucket="tiles",
        prefix="",
        layout="auto",
        matrix_set="webmercator",
        output_dir=tmp_path,
        summary_path=tmp_path / "tiles-summary.json",
        stdout=stdout,
    )

    output = stdout.getvalue()

    assert "Total tile count: 1,234" in output
    assert "   11  1,234" in output
    assert "2026-01-02" in output
    assert "2026-01-03" in output
    assert date_created.isoformat() not in output
    assert date_last_modified.isoformat() not in output
    assert "Output file" not in output


def test_print_summary_formats_date_ranges_as_dates(tmp_path):
    inventory = cli.build_inventory(
        [
            source_object(
                "3/0/0",
                date_created=datetime(2025, 7, 29, 5, 39, 25, tzinfo=UTC),
                date_last_modified=datetime(2025, 7, 29, 5, 39, 25, tzinfo=UTC),
            ),
            source_object(
                "3/1/0",
                date_created=datetime(2025, 7, 30, 1, 2, 3, tzinfo=UTC),
                date_last_modified=datetime(2025, 8, 1, 4, 5, 6, tzinfo=UTC),
            ),
        ],
        layout="auto",
        level_filter=None,
    )
    stdout = StringIO()

    cli.print_summary(
        inventory=inventory,
        stats=inventory.level_stats(),
        bucket="tiles",
        prefix="",
        layout="auto",
        matrix_set="webmercator",
        output_dir=tmp_path,
        summary_path=tmp_path / "tiles-summary.json",
        stdout=stdout,
    )

    output = stdout.getvalue()

    assert "2025-07-29 to 2025-07-30" in output
    assert "2025-07-29 to 2025-08-01" in output
    assert "05:39:25" not in output


def test_inventory_cli_progress_always_updates_listing_and_writing(monkeypatch, tmp_path, capsys):
    def fake_list_source_objects(*, bucket_name, prefix, project):
        return [
            source_object("Terrain/0/0/0"),
            source_object("Terrain/1/0/0"),
            source_object("Terrain/1/1/1"),
            source_object("Terrain/readme.txt"),
        ]

    events = []

    class FakeTqdm:
        def __init__(self, *, total, desc, unit, file, bar_format, **_kwargs):
            self.desc = desc
            self.file = file
            events.append(("start", desc, total, unit, bar_format))
            print(desc, file=file)

        def update(self, n=1):
            events.append(("update", self.desc, n))

        def close(self):
            events.append(("close", self.desc))

    fake_tqdm = types.ModuleType("tqdm")
    fake_tqdm.tqdm = FakeTqdm
    monkeypatch.setitem(sys.modules, "tqdm", fake_tqdm)
    monkeypatch.setattr(cli, "list_source_objects", fake_list_source_objects)

    exit_code = cli.main(
        [
            "inventory",
            "tiles",
            "--output",
            str(tmp_path),
            "--prefix",
            "Terrain/",
            "--progress",
            "always",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Overall progress" in captured.err
    assert (
        "start",
        "Overall progress",
        2,
        " phases",
        "{desc}: {n_fmt}/{total_fmt} phases",
    ) in events
    assert (
        "start",
        "Listing and parsing objects",
        None,
        " objects",
        "{desc}: {n_fmt} objects [{elapsed}, {rate_fmt}]",
    ) in events
    assert (
        "start",
        "Writing GeoPackage features",
        3,
        " tiles",
        "{desc}: {percentage:3.0f}%|{bar}| "
        "{n_fmt}/{total_fmt} tiles [{elapsed}<{remaining}, {rate_fmt}]",
    ) in events
    assert events.count(("update", "Listing and parsing objects", 1)) == 4
    assert events.count(("update", "Writing GeoPackage features", 1)) == 3


def test_inventory_cli_rejects_invalid_levels(tmp_path, capsys):
    exit_code = cli.main(["inventory", "tiles", "--output", str(tmp_path), "--levels", "3-1"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Invalid --levels" in captured.err


def test_inventory_cli_writes_summary_when_no_matching_tiles(monkeypatch, tmp_path, capsys):
    def fake_list_source_objects(*, bucket_name, prefix, project):
        return [source_object("metadata.json")]

    monkeypatch.setattr(cli, "list_source_objects", fake_list_source_objects)

    exit_code = cli.main(["inventory", "tiles", "--output", str(tmp_path)])

    captured = capsys.readouterr()
    summary = json.loads((tmp_path / "tiles-summary.json").read_text(encoding="utf-8"))

    assert exit_code == 1
    assert "No matching tiles found." in captured.err
    assert summary["total_tile_count"] == 0
    assert summary["generated_file_count"] == 0


def test_inventory_cli_rejects_removed_format_option(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                "inventory",
                "tiles",
                "--output",
                str(tmp_path),
                "--format",
                "geojson",
            ]
        )

    assert exc_info.value.code == 2


def test_inventory_cli_help_does_not_include_format_option(capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            [
                "inventory",
                "--help",
            ]
        )

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert "--format" not in captured.out
    assert "GeoPackage" in captured.out
