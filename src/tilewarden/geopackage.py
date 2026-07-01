"""GeoPackage writer for per-level tile footprint layers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import geopandas as gpd
from shapely import Polygon

from tilewarden.footprints import WEBMERCATOR_WKID, webmercator_tile_ring
from tilewarden.inventory import Tile


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

    for index, (level, tiles) in enumerate(sorted(tiles_by_level.items())):
        _write_level_layer(
            path,
            level=level,
            bucket=bucket,
            prefix=prefix,
            layout=layout,
            matrix_set=matrix_set,
            tiles=tiles,
            progress=progress,
            append=index > 0,
        )

    return path


def _level_table_name(level: int) -> str:
    return f"tile_footprints_l{level:02d}"


def _write_level_layer(
    path: Path,
    *,
    level: int,
    bucket: str,
    prefix: str,
    layout: str,
    matrix_set: str,
    tiles: list[Tile],
    progress: Callable[[], None] | None,
    append: bool,
) -> None:
    rows: list[dict[str, object]] = []
    for tile in tiles:
        rows.append(
            {
                "bucket": bucket,
                "prefix": prefix,
                "layout": layout,
                "matrix_set": matrix_set,
                "level": tile.level,
                "column": tile.column,
                "row": tile.row,
                "blob_name": tile.blob_name,
                "date_created": _isoformat(tile.date_created),
                "date_last_modified": _isoformat(tile.date_last_modified),
                "wkid": WEBMERCATOR_WKID,
                "geom": Polygon(webmercator_tile_ring(tile)),
            }
        )
        if progress is not None:
            progress()

    frame = gpd.GeoDataFrame(rows, geometry="geom", crs=f"EPSG:{WEBMERCATOR_WKID}")
    frame.to_file(
        path,
        layer=_level_table_name(level),
        driver="GPKG",
        mode="a" if append else "w",
    )


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _safe_name(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "_"
        for character in value
    )
