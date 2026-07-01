"""Pure parsers for CLI level filters and tiled object layouts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

SUPPORTED_LAYOUTS = frozenset(
    {
        "auto",
        "z/x/y",
        "prefix/z/x/y",
        "z/x/y.ext",
        "prefix/z/x/y.ext",
        "z/y/x",
        "prefix/z/y/x",
    }
)


@dataclass(frozen=True, slots=True)
class ParsedTile:
    level: int
    column: int
    row: int
    blob_name: str


class LevelParseError(ValueError):
    """Raised when a level filter cannot be parsed."""


class LayoutParseError(ValueError):
    """Raised when a layout name is unsupported."""


def parse_level_filter(value: str | None) -> set[int] | None:
    """Parse a level filter into a sorted set, or None for all discovered levels."""

    if value is None or value.strip() == "":
        return None

    levels: set[int] = set()
    for raw_part in value.split(","):
        part = raw_part.strip()
        if not part:
            raise LevelParseError("Level filters cannot contain empty entries.")

        if "-" in part:
            start_text, separator, end_text = part.partition("-")
            if separator != "-" or not start_text or not end_text:
                raise LevelParseError(f"Invalid level range: {part!r}.")
            start = _parse_nonnegative_int(start_text, "level range start")
            end = _parse_nonnegative_int(end_text, "level range end")
            if start > end:
                raise LevelParseError(f"Invalid descending level range: {part!r}.")
            levels.update(range(start, end + 1))
        else:
            levels.add(_parse_nonnegative_int(part, "level"))

    return set(sorted(levels))


def parse_blob_name(blob_name: str, layout: str = "auto") -> ParsedTile | None:
    """Parse a GCS blob name as a tile path, returning None for non-tile objects."""

    if layout not in SUPPORTED_LAYOUTS:
        supported = ", ".join(sorted(SUPPORTED_LAYOUTS))
        raise LayoutParseError(f"Unsupported layout {layout!r}. Expected one of: {supported}.")

    parts = [part for part in PurePosixPath(blob_name).parts if part not in {"/", ""}]
    if layout == "auto":
        return _parse_xyz_parts(blob_name, parts[-3:], final_component_has_extension=True)

    needs_prefix = layout.startswith("prefix/")
    ordered = layout.removeprefix("prefix/")
    required_length = 4 if needs_prefix else 3
    if len(parts) != required_length:
        return None

    tile_parts = parts[-3:]
    final_component_has_extension = ordered.endswith(".ext")
    if ordered.startswith("z/x/y"):
        return _parse_xyz_parts(blob_name, tile_parts, final_component_has_extension)
    if ordered == "z/y/x":
        return _parse_zyx_parts(blob_name, tile_parts)

    raise LayoutParseError(f"Unsupported layout {layout!r}.")


def resolve_layout(blob_name: str, layout: str = "auto") -> str | None:
    """Resolve the concrete layout for a blob name, if one can be identified."""

    if layout not in SUPPORTED_LAYOUTS:
        supported = ", ".join(sorted(SUPPORTED_LAYOUTS))
        raise LayoutParseError(f"Unsupported layout {layout!r}. Expected one of: {supported}.")

    if layout != "auto":
        return layout

    parts = [part for part in PurePosixPath(blob_name).parts if part not in {"/", ""}]
    if len(parts) < 3:
        return None

    parsed = _parse_xyz_parts(blob_name, parts[-3:], final_component_has_extension=True)
    if parsed is None:
        return None

    has_prefix = len(parts) > 3
    has_extension = bool(PurePosixPath(parts[-1]).suffix)
    resolved = "z/x/y"
    if has_extension:
        resolved += ".ext"
    if has_prefix:
        resolved = f"prefix/{resolved}"
    return resolved


def resolve_prefix(blob_name: str, layout: str = "auto") -> str | None:
    """Resolve the concrete tile prefix for a blob name, if one can be identified."""

    resolved_layout = resolve_layout(blob_name, layout)
    if resolved_layout is None:
        return None
    if not resolved_layout.startswith("prefix/"):
        return ""

    parts = [part for part in PurePosixPath(blob_name).parts if part not in {"/", ""}]
    if len(parts) < 4:
        return None
    return f"{parts[0]}/"


def _parse_xyz_parts(
    blob_name: str,
    parts: list[str] | tuple[str, ...],
    final_component_has_extension: bool,
) -> ParsedTile | None:
    if len(parts) != 3:
        return None

    level_text, column_text, row_text = parts
    if final_component_has_extension:
        row_text = _strip_extension(row_text)

    values = _parse_tile_numbers(level_text, column_text, row_text)
    if values is None:
        return None
    level, column, row = values
    return ParsedTile(level=level, column=column, row=row, blob_name=blob_name)


def _parse_zyx_parts(blob_name: str, parts: list[str] | tuple[str, ...]) -> ParsedTile | None:
    if len(parts) != 3:
        return None

    level_text, row_text, column_text = parts
    values = _parse_tile_numbers(level_text, column_text, row_text)
    if values is None:
        return None
    level, column, row = values
    return ParsedTile(level=level, column=column, row=row, blob_name=blob_name)


def _parse_tile_numbers(
    level_text: str, column_text: str, row_text: str
) -> tuple[int, int, int] | None:
    try:
        level = _parse_nonnegative_int(level_text, "level")
        column = _parse_nonnegative_int(column_text, "column")
        row = _parse_nonnegative_int(row_text, "row")
    except LevelParseError:
        return None
    return level, column, row


def _parse_nonnegative_int(value: str, label: str) -> int:
    if not value.isdecimal():
        raise LevelParseError(f"Invalid {label}: {value!r}.")
    parsed = int(value)
    if parsed < 0:
        raise LevelParseError(f"Invalid negative {label}: {value!r}.")
    return parsed


def _strip_extension(value: str) -> str:
    suffix = PurePosixPath(value).suffix
    if suffix:
        return value[: -len(suffix)]
    return value
