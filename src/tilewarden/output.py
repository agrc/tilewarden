"""GeoPackage and summary writers for tile inventories."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from tilewarden.geopackage import write_inventory_geopackage
from tilewarden.inventory import Inventory, LevelStats


def write_inventory_outputs(
    inventory: Inventory,
    *,
    output_dir: Path,
    bucket: str,
    prefix: str,
    layout: str,
    matrix_set: str,
    levels_option: str | None,
    processing_time_seconds: float,
    progress: Callable[[], None] | None = None,
) -> tuple[dict[int, Path], Path, dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)

    effective_layout = inventory.resolved_layout or layout
    effective_prefix = (
        inventory.resolved_prefix if inventory.resolved_prefix is not None else prefix
    )

    output_files: dict[int, Path] = {}
    if inventory.tiles_by_level:
        geopackage_path = write_inventory_geopackage(
            output_dir=output_dir,
            bucket=bucket,
            prefix=effective_prefix,
            layout=effective_layout,
            matrix_set=matrix_set,
            tiles_by_level=inventory.tiles_by_level,
            progress=progress,
        )
        output_files = {level: geopackage_path for level in inventory.tiles_by_level}

    stats = inventory.level_stats(output_files)
    summary = build_summary(
        inventory=inventory,
        bucket=bucket,
        prefix=effective_prefix,
        layout=effective_layout,
        matrix_set=matrix_set,
        levels_option=levels_option,
        output_dir=output_dir,
        stats=stats,
        processing_time_seconds=processing_time_seconds,
    )
    summary_path = output_dir / f"{_safe_name(bucket)}-summary.json"
    with summary_path.open("w", encoding="utf-8") as summary_file:
        json.dump(summary, summary_file, indent=2)
        summary_file.write("\n")

    return output_files, summary_path, summary


def build_summary(
    *,
    inventory: Inventory,
    bucket: str,
    prefix: str,
    layout: str,
    matrix_set: str,
    levels_option: str | None,
    output_dir: Path,
    stats: list[LevelStats],
    processing_time_seconds: float,
) -> dict[str, object]:
    generated_files = sorted(
        {str(stat.output_file) for stat in stats if stat.output_file is not None}
    )
    dates_created = [
        tile.date_created
        for tiles in inventory.tiles_by_level.values()
        for tile in tiles
        if tile.date_created is not None
    ]
    dates_last_modified = [
        tile.date_last_modified
        for tiles in inventory.tiles_by_level.values()
        for tile in tiles
        if tile.date_last_modified is not None
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "bucket": bucket,
        "prefix": prefix,
        "layout": layout,
        "matrix_set": matrix_set,
        "levels": levels_option,
        "output_dir": str(output_dir),
        "total_processing_time_seconds": round(processing_time_seconds, 3),
        "skipped_object_count": inventory.skipped_object_count,
        "excluded_by_level_count": inventory.excluded_by_level_count,
        "total_tile_count": inventory.total_tile_count,
        "min_date_created": _isoformat(min(dates_created) if dates_created else None),
        "max_date_created": _isoformat(max(dates_created) if dates_created else None),
        "min_date_last_modified": _isoformat(
            min(dates_last_modified) if dates_last_modified else None
        ),
        "max_date_last_modified": _isoformat(
            max(dates_last_modified) if dates_last_modified else None
        ),
        "generated_file_count": len(generated_files),
        "generated_files": generated_files,
        "levels_summary": [
            {
                "level": stat.level,
                "tile_count": stat.tile_count,
                "min_column": stat.min_column,
                "max_column": stat.max_column,
                "min_row": stat.min_row,
                "max_row": stat.max_row,
                "min_date_created": _isoformat(stat.min_date_created),
                "max_date_created": _isoformat(stat.max_date_created),
                "min_date_last_modified": _isoformat(stat.min_date_last_modified),
                "max_date_last_modified": _isoformat(stat.max_date_last_modified),
                "output_file": str(stat.output_file) if stat.output_file is not None else None,
            }
            for stat in stats
        ],
    }


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _safe_name(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "_"
        for character in value
    )
