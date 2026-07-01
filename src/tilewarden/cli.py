"""Command line interface for tilewarden."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Protocol, TextIO

import humanize

from tilewarden.gcs import GCSListingError, discover_listing_parameters, list_source_objects
from tilewarden.inventory import build_inventory
from tilewarden.output import write_inventory_outputs
from tilewarden.parsing import (
    SUPPORTED_LAYOUTS,
    LayoutParseError,
    LevelParseError,
    parse_level_filter,
)

MATRIX_SETS = ("webmercator",)


class _ProgressBar(Protocol):
    def update(self, n: float | None = 1) -> bool | None: ...

    def close(self) -> None: ...


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "inventory":
        return run_inventory(args, stdout=sys.stdout, stderr=sys.stderr)

    parser.print_help(sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tilewarden",
        description="Inventory tiled map objects and write GeoPackage footprint layers.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory_parser = subparsers.add_parser(
        "inventory",
        help="Inventory a Google Cloud Storage bucket.",
        description=(
            "Inventory a Google Cloud Storage bucket and write one GeoPackage "
            "with a separate layer per level."
        ),
    )
    inventory_parser.add_argument(
        "bucket_name", metavar="bucket-name", help="GCS bucket name to list."
    )
    inventory_parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output directory for the GeoPackage footprint file and summary JSON file.",
    )
    inventory_parser.add_argument(
        "--levels",
        help="Level filter such as '5', '5-7', or '5,7,10-12'. Omit for all discovered levels.",
    )
    inventory_parser.add_argument(
        "--prefix", default="", help="Optional GCS object prefix to list."
    )
    inventory_parser.add_argument(
        "--layout",
        default="auto",
        choices=sorted(SUPPORTED_LAYOUTS),
        help="Object layout parser to use. Defaults to auto.",
    )
    inventory_parser.add_argument(
        "--project", help="Optional Google Cloud project for the storage client."
    )
    inventory_parser.add_argument(
        "--matrix-set",
        default="webmercator",
        choices=MATRIX_SETS,
        help="Tile matrix set. Only webmercator is currently supported.",
    )
    inventory_parser.add_argument(
        "--progress",
        default="auto",
        choices=("auto", "always", "never"),
        help="Show progress bars and ETA. Defaults to auto, which enables progress in terminals.",
    )
    return parser


def run_inventory(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    start_time = perf_counter()

    try:
        level_filter = parse_level_filter(args.levels)
    except LevelParseError as exc:
        print(f"Invalid --levels: {exc}", file=stderr)
        return 2

    effective_prefix = args.prefix
    effective_layout = args.layout
    if _should_discover_listing(prefix=args.prefix, layout=args.layout):
        try:
            discovered = discover_listing_parameters(
                bucket_name=args.bucket_name,
                prefix=args.prefix,
                layout=args.layout,
                project=args.project,
            )
        except GCSListingError as exc:
            print(str(exc), file=stderr)
            return 1
        if discovered is not None:
            if args.layout == "auto":
                effective_layout = discovered.layout
            if args.prefix == "":
                effective_prefix = discovered.prefix

    progress_enabled = _should_show_progress(args.progress, stderr)
    overall_progress = _make_progress_bar(
        enabled=progress_enabled,
        stderr=stderr,
        total=2,
        desc="Overall progress",
        unit=" phases",
        bar_format="{desc}: {n:,.0f}/{total:,.0f} phases",
    )
    try:
        inventory_progress = _make_progress_bar(
            enabled=progress_enabled,
            stderr=stderr,
            total=None,
            desc="Listing and parsing objects",
            unit=" objects",
            bar_format="{desc}: {n:,.0f} objects [{elapsed}, {rate_fmt}]",
        )
        try:
            inventory = build_inventory(
                list_source_objects(
                    bucket_name=args.bucket_name,
                    prefix=effective_prefix,
                    layout=effective_layout,
                    level_filter=level_filter,
                    project=args.project,
                ),
                layout=effective_layout,
                level_filter=level_filter,
                progress=_progress_update(inventory_progress),
            )
        except LayoutParseError as exc:
            print(f"Invalid --layout: {exc}", file=stderr)
            return 2
        except GCSListingError as exc:
            print(str(exc), file=stderr)
            return 1
        finally:
            if inventory_progress is not None:
                inventory_progress.close()

        if overall_progress is not None:
            overall_progress.update()

        write_progress = _make_progress_bar(
            enabled=progress_enabled and inventory.total_tile_count > 0,
            stderr=stderr,
            total=inventory.total_tile_count,
            desc="Writing GeoPackage features",
            unit=" tiles",
            bar_format=(
                "{desc}: {percentage:3.0f}%|{bar}| "
                "{n:,.0f}/{total:,.0f} tiles [{elapsed}<{remaining}, {rate_fmt}]"
            ),
        )
        try:
            output_files, summary_path, _summary = write_inventory_outputs(
                inventory,
                output_dir=args.output,
                bucket=args.bucket_name,
                prefix=effective_prefix,
                layout=effective_layout,
                matrix_set=args.matrix_set,
                levels_option=args.levels,
                processing_time_seconds=perf_counter() - start_time,
                progress=_progress_update(write_progress),
            )
        except OSError as exc:
            print(f"Could not write output: {exc}", file=stderr)
            return 1
        finally:
            if write_progress is not None:
                write_progress.close()

        if overall_progress is not None:
            overall_progress.update()
    finally:
        if overall_progress is not None:
            overall_progress.close()

    stats = inventory.level_stats(output_files)
    summary_prefix = (
        inventory.resolved_prefix if inventory.resolved_prefix is not None else effective_prefix
    )
    summary_layout = inventory.resolved_layout or effective_layout
    print_summary(
        inventory=inventory,
        stats=stats,
        bucket=args.bucket_name,
        prefix=summary_prefix,
        layout=summary_layout,
        matrix_set=args.matrix_set,
        output_dir=args.output,
        summary_path=summary_path,
        processing_time_seconds=perf_counter() - start_time,
        stdout=stdout,
    )

    if inventory.total_tile_count == 0:
        print("No matching tiles found.", file=stderr)
        return 1
    return 0


def _should_discover_listing(*, prefix: str, layout: str) -> bool:
    return layout == "auto" or (prefix == "" and layout.startswith("prefix/"))


def _should_show_progress(progress: str, stderr: TextIO) -> bool:
    if progress == "always":
        return True
    if progress == "never":
        return False
    return stderr.isatty()


def _make_progress_bar(
    *,
    enabled: bool,
    stderr: TextIO,
    total: int | None,
    desc: str,
    unit: str,
    bar_format: str,
) -> _ProgressBar | None:
    if not enabled:
        return None

    from tqdm import tqdm

    return tqdm(
        total=total,
        desc=desc,
        unit=unit,
        file=stderr,
        bar_format=bar_format,
        dynamic_ncols=True,
        mininterval=0.5,
    )


def _progress_update(progress_bar: _ProgressBar | None) -> Callable[[], None] | None:
    if progress_bar is None:
        return None

    def update() -> None:
        progress_bar.update()

    return update


def print_summary(
    *,
    inventory,
    stats,
    bucket: str,
    prefix: str,
    layout: str,
    matrix_set: str,
    output_dir: Path,
    summary_path: Path,
    processing_time_seconds: float,
    stdout: TextIO,
) -> None:
    print("Tile inventory complete", file=stdout)
    print(f"Bucket: {bucket}", file=stdout)
    print(f"Prefix: {prefix or '(none)'}", file=stdout)
    print(f"Layout: {layout}", file=stdout)
    print(f"Matrix set: {matrix_set}", file=stdout)
    print(f"Output directory: {output_dir}", file=stdout)
    print(f"Skipped object count: {inventory.skipped_object_count:,}", file=stdout)
    print(f"Excluded by level count: {inventory.excluded_by_level_count:,}", file=stdout)
    print(f"Total tile count: {inventory.total_tile_count:,}", file=stdout)
    print(
        f"Total processing time: {_format_duration_seconds(processing_time_seconds)}",
        file=stdout,
    )
    generated_file_count = len({stat.output_file for stat in stats if stat.output_file is not None})
    print(f"Generated file count: {generated_file_count:,}", file=stdout)
    print(f"Summary JSON path: {summary_path}", file=stdout)

    if not stats:
        return

    print("", file=stdout)
    rows = [
        (
            str(stat.level),
            f"{stat.tile_count:,}",
            _date_range(stat.min_date_last_modified, stat.max_date_last_modified),
        )
        for stat in stats
    ]
    headers = ("Level", "Tiles", "Last modified")
    widths = tuple(
        max(len(header), *(len(row[index]) for row in rows)) for index, header in enumerate(headers)
    )
    print(_format_summary_row(headers, widths), file=stdout)
    print("  ".join("-" * width for width in widths), file=stdout)
    for row in rows:
        print(_format_summary_row(row, widths), file=stdout)


def _date_range(start, end) -> str:
    if start is None or end is None:
        return "(none)"
    start_date = start.date().isoformat()
    end_date = end.date().isoformat()
    if start_date == end_date:
        return start_date
    return f"{start_date} to {end_date}"


def _format_summary_row(row, widths) -> str:
    level, tiles, last_modified = row
    level_width, tiles_width, last_modified_width = widths
    return f"{level:>{level_width}}  {tiles:>{tiles_width}}  {last_modified:<{last_modified_width}}"


def _format_duration_seconds(seconds: float) -> str:
    return humanize.precisedelta(seconds, minimum_unit="seconds", format="%0.3f")
