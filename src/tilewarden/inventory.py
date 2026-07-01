"""Tile inventory data model and aggregation helpers."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from tilewarden.parsing import parse_blob_name, resolve_layout, resolve_prefix


@dataclass(frozen=True, slots=True)
class SourceObject:
    name: str
    date_created: datetime | None
    date_last_modified: datetime | None


@dataclass(frozen=True, slots=True)
class Tile:
    level: int
    column: int
    row: int
    blob_name: str
    date_created: datetime | None
    date_last_modified: datetime | None


@dataclass(frozen=True, slots=True)
class LevelStats:
    level: int
    tile_count: int
    min_column: int
    max_column: int
    min_row: int
    max_row: int
    min_date_created: datetime | None
    max_date_created: datetime | None
    min_date_last_modified: datetime | None
    max_date_last_modified: datetime | None
    output_file: Path | None = None


@dataclass(slots=True)
class Inventory:
    tiles_by_level: dict[int, list[Tile]] = field(default_factory=dict)
    skipped_object_count: int = 0
    excluded_by_level_count: int = 0
    resolved_layout: str | None = None
    resolved_prefix: str | None = None

    @property
    def total_tile_count(self) -> int:
        return sum(len(tiles) for tiles in self.tiles_by_level.values())

    def level_stats(self, output_files: dict[int, Path] | None = None) -> list[LevelStats]:
        stats: list[LevelStats] = []
        for level in sorted(self.tiles_by_level):
            tiles = self.tiles_by_level[level]
            columns = [tile.column for tile in tiles]
            rows = [tile.row for tile in tiles]
            dates_created = [tile.date_created for tile in tiles if tile.date_created is not None]
            dates_last_modified = [
                tile.date_last_modified for tile in tiles if tile.date_last_modified is not None
            ]
            stats.append(
                LevelStats(
                    level=level,
                    tile_count=len(tiles),
                    min_column=min(columns),
                    max_column=max(columns),
                    min_row=min(rows),
                    max_row=max(rows),
                    min_date_created=min(dates_created) if dates_created else None,
                    max_date_created=max(dates_created) if dates_created else None,
                    min_date_last_modified=min(dates_last_modified)
                    if dates_last_modified
                    else None,
                    max_date_last_modified=max(dates_last_modified)
                    if dates_last_modified
                    else None,
                    output_file=(output_files or {}).get(level),
                )
            )
        return stats


def build_inventory(
    source_objects: Iterable[SourceObject],
    *,
    layout: str,
    level_filter: set[int] | None,
    progress: Callable[[], None] | None = None,
) -> Inventory:
    """Build an inventory from blob names, skipping non-tile objects."""

    grouped_tiles: dict[int, list[Tile]] = defaultdict(list)
    skipped_object_count = 0
    excluded_by_level_count = 0
    resolved_layout_name: str | None = None
    resolved_prefix_value: str | None = None

    for source_object in source_objects:
        if progress is not None:
            progress()

        parsed = parse_blob_name(source_object.name, layout)
        if parsed is not None and resolved_layout_name is None:
            resolved_layout_name = resolve_layout(source_object.name, layout)
        if parsed is not None and resolved_prefix_value is None:
            resolved_prefix_value = resolve_prefix(source_object.name, layout)
        if parsed is None or not is_valid_webmercator_tile(parsed.level, parsed.column, parsed.row):
            skipped_object_count += 1
            continue

        if level_filter is not None and parsed.level not in level_filter:
            excluded_by_level_count += 1
            continue

        tile = Tile(
            level=parsed.level,
            column=parsed.column,
            row=parsed.row,
            blob_name=parsed.blob_name,
            date_created=source_object.date_created,
            date_last_modified=source_object.date_last_modified,
        )
        grouped_tiles[tile.level].append(tile)

    for tiles in grouped_tiles.values():
        tiles.sort(key=lambda tile: (tile.row, tile.column, tile.blob_name))

    return Inventory(
        tiles_by_level=dict(sorted(grouped_tiles.items())),
        skipped_object_count=skipped_object_count,
        excluded_by_level_count=excluded_by_level_count,
        resolved_layout=resolved_layout_name,
        resolved_prefix=resolved_prefix_value,
    )


def is_valid_webmercator_tile(level: int, column: int, row: int) -> bool:
    matrix_size = 2**level
    return 0 <= column < matrix_size and 0 <= row < matrix_size
