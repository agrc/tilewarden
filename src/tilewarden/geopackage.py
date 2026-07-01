"""Minimal GeoPackage writer for per-level tile footprint layers."""

from __future__ import annotations

import sqlite3
import struct
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from tilewarden.footprints import (
    WEBMERCATOR_WKID,
    webmercator_tile_bounds,
    webmercator_tile_ring,
)
from tilewarden.inventory import Tile

GPKG_APPLICATION_ID = 1196444487
GPKG_USER_VERSION = 10400
WEBMERCATOR_DEFINITION = (
    'PROJCS["WGS 84 / Pseudo-Mercator",'
    'GEOGCS["WGS 84",'
    'DATUM["WGS_1984",'
    'SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],'
    'AUTHORITY["EPSG","6326"]],'
    'PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],'
    'UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],'
    'AUTHORITY["EPSG","4326"]],'
    'PROJECTION["Mercator_1SP"],'
    'PARAMETER["central_meridian",0],'
    'PARAMETER["scale_factor",1],'
    'PARAMETER["false_easting",0],'
    'PARAMETER["false_northing",0],'
    'UNIT["metre",1,AUTHORITY["EPSG","9001"]],'
    'AXIS["X",EAST],'
    'AXIS["Y",NORTH],'
    'AUTHORITY["EPSG","3857"]]'
)


def write_inventory_geopackage(
    *,
    output_dir: Path,
    bucket: str,
    prefix: str,
    layout: str,
    matrix_set: str,
    tiles_by_level: dict[int, list[Tile]],
    progress: Callable[[], None] | None = None,
) -> Path:
    path = output_dir / f"{_safe_name(bucket)}-tile-footprints.gpkg"
    if path.exists():
        path.unlink()

    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.execute(f"PRAGMA application_id = {GPKG_APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version = {GPKG_USER_VERSION}")
            _create_metadata_tables(connection)
            for level, tiles in sorted(tiles_by_level.items()):
                table_name = _level_table_name(level)
                _create_feature_table(connection, table_name)
                _register_feature_table(connection, table_name, level, tiles)
                _create_spatial_index(connection, table_name)
                _insert_tiles(
                    connection,
                    table_name=table_name,
                    bucket=bucket,
                    prefix=prefix,
                    layout=layout,
                    matrix_set=matrix_set,
                    tiles=tiles,
                    progress=progress,
                )
    finally:
        connection.close()

    return path


def _level_table_name(level: int) -> str:
    return f"tile_footprints_l{level:02d}"


def _create_metadata_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE gpkg_spatial_ref_sys (
            srs_name TEXT NOT NULL,
            srs_id INTEGER NOT NULL PRIMARY KEY,
            organization TEXT NOT NULL,
            organization_coordsys_id INTEGER NOT NULL,
            definition TEXT NOT NULL,
            description TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE gpkg_contents (
            table_name TEXT NOT NULL PRIMARY KEY,
            data_type TEXT NOT NULL,
            identifier TEXT UNIQUE,
            description TEXT DEFAULT '',
            last_change DATETIME NOT NULL,
            min_x DOUBLE,
            min_y DOUBLE,
            max_x DOUBLE,
            max_y DOUBLE,
            srs_id INTEGER,
            FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE gpkg_geometry_columns (
            table_name TEXT NOT NULL,
            column_name TEXT NOT NULL,
            geometry_type_name TEXT NOT NULL,
            srs_id INTEGER NOT NULL,
            z TINYINT NOT NULL,
            m TINYINT NOT NULL,
            PRIMARY KEY (table_name, column_name),
            FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name),
            FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE gpkg_extensions (
            table_name TEXT,
            column_name TEXT,
            extension_name TEXT NOT NULL,
            definition TEXT NOT NULL,
            scope TEXT NOT NULL,
            CONSTRAINT ge_tce UNIQUE (table_name, column_name, extension_name)
        )
        """
    )
    connection.executemany(
        """
        INSERT INTO gpkg_spatial_ref_sys (
            srs_name, srs_id, organization, organization_coordsys_id,
            definition, description
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "Undefined Cartesian SRS",
                -1,
                "NONE",
                -1,
                "undefined",
                "undefined cartesian",
            ),
            (
                "Undefined Geographic SRS",
                0,
                "NONE",
                0,
                "undefined",
                "undefined geographic",
            ),
            (
                "WGS 84 / Pseudo-Mercator",
                WEBMERCATOR_WKID,
                "EPSG",
                WEBMERCATOR_WKID,
                WEBMERCATOR_DEFINITION,
                "Web Mercator Auxiliary Sphere",
            ),
        ],
    )


def _create_feature_table(connection: sqlite3.Connection, table_name: str) -> None:
    quoted_table = _quote_identifier(table_name)
    connection.execute(
        f"""
        CREATE TABLE {quoted_table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            geom BLOB NOT NULL,
            bucket TEXT NOT NULL,
            prefix TEXT NOT NULL,
            layout TEXT NOT NULL,
            matrix_set TEXT NOT NULL,
            level INTEGER NOT NULL,
            column INTEGER NOT NULL,
            row INTEGER NOT NULL,
            blob_name TEXT NOT NULL,
            date_created TEXT,
            date_last_modified TEXT,
            wkid INTEGER NOT NULL
        )
        """
    )


def _register_feature_table(
    connection: sqlite3.Connection, table_name: str, level: int, tiles: list[Tile]
) -> None:
    min_x, min_y, max_x, max_y = _dataset_bounds(tiles)
    connection.execute(
        """
        INSERT INTO gpkg_contents (
            table_name, data_type, identifier, description, last_change,
            min_x, min_y, max_x, max_y, srs_id
        ) VALUES (?, 'features', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            table_name,
            f"tile_footprints_l{level:02d}",
            f"Tile footprints for level {level}",
            datetime.now(UTC).isoformat(timespec="milliseconds"),
            min_x,
            min_y,
            max_x,
            max_y,
            WEBMERCATOR_WKID,
        ),
    )
    connection.execute(
        """
        INSERT INTO gpkg_geometry_columns (
            table_name, column_name, geometry_type_name, srs_id, z, m
        ) VALUES (?, 'geom', 'POLYGON', ?, 0, 0)
        """,
        (table_name, WEBMERCATOR_WKID),
    )


def _create_spatial_index(connection: sqlite3.Connection, table_name: str) -> None:
    rtree_name = _quote_identifier(f"rtree_{table_name}_geom")
    connection.execute(f"CREATE VIRTUAL TABLE {rtree_name} USING rtree(id, minx, maxx, miny, maxy)")
    extension_url = "http://www.geopackage.org/spec/#extension_rtree"
    connection.execute(
        """
        INSERT INTO gpkg_extensions (
            table_name, column_name, extension_name, definition, scope
        ) VALUES (?, 'geom', 'gpkg_rtree_index', ?, 'write-only')
        """,
        (table_name, extension_url),
    )


def _insert_tiles(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    bucket: str,
    prefix: str,
    layout: str,
    matrix_set: str,
    tiles: list[Tile],
    progress: Callable[[], None] | None,
) -> None:
    quoted_table = _quote_identifier(table_name)
    quoted_rtree = _quote_identifier(f"rtree_{table_name}_geom")

    for tile in tiles:
        cursor = connection.execute(
            f"""
            INSERT INTO {quoted_table} (
                geom, bucket, prefix, layout, matrix_set, level, column, row, blob_name,
                date_created, date_last_modified, wkid
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _geopackage_polygon(tile),
                bucket,
                prefix,
                layout,
                matrix_set,
                tile.level,
                tile.column,
                tile.row,
                tile.blob_name,
                _isoformat(tile.date_created),
                _isoformat(tile.date_last_modified),
                WEBMERCATOR_WKID,
            ),
        )
        left, bottom, right, top = webmercator_tile_bounds(tile)
        connection.execute(
            (f"INSERT INTO {quoted_rtree} (id, minx, maxx, miny, maxy) VALUES (?, ?, ?, ?, ?)"),
            (cursor.lastrowid, left, right, bottom, top),
        )
        if progress is not None:
            progress()


def _geopackage_polygon(tile: Tile) -> bytes:
    header = struct.pack("<2sBBi", b"GP", 0, 1, WEBMERCATOR_WKID)
    ring = webmercator_tile_ring(tile)

    parts = [
        header,
        struct.pack("<BI", 1, 3),
        struct.pack("<I", 1),
        struct.pack("<I", len(ring)),
    ]
    parts.extend(struct.pack("<dd", x, y) for x, y in ring)
    return b"".join(parts)


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _dataset_bounds(tiles: list[Tile]) -> tuple[float, float, float, float]:
    bounds = [webmercator_tile_bounds(tile) for tile in tiles]
    return (
        min(left for left, _bottom, _right, _top in bounds),
        min(bottom for _left, bottom, _right, _top in bounds),
        max(right for _left, _bottom, right, _top in bounds),
        max(top for _left, _bottom, _right, top in bounds),
    )


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _safe_name(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "_"
        for character in value
    )
