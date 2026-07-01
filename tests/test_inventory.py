from datetime import UTC, datetime

from tilewarden.inventory import SourceObject, build_inventory


def source_object(
    name,
    *,
    date_created=None,
    date_last_modified=None,
):
    return SourceObject(
        name=name,
        date_created=date_created,
        date_last_modified=date_last_modified,
    )


def test_build_inventory_groups_tiles_and_stats():
    date_created = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    date_last_modified = datetime(2026, 1, 3, 3, 4, 5, tzinfo=UTC)
    inventory = build_inventory(
        [
            source_object("Terrain/2/1/2", date_created=date_created),
            source_object(
                "Terrain/2/2/3",
                date_created=datetime(2026, 1, 4, 3, 4, 5, tzinfo=UTC),
                date_last_modified=date_last_modified,
            ),
            source_object("Terrain/1/1/1"),
            source_object("Terrain/info.json"),
        ],
        layout="auto",
        level_filter=None,
    )

    assert inventory.skipped_object_count == 1
    assert inventory.total_tile_count == 3
    assert inventory.resolved_layout == "prefix/z/x/y"
    assert inventory.resolved_prefix == "Terrain/"

    stats = inventory.level_stats()
    assert [(stat.level, stat.tile_count) for stat in stats] == [(1, 1), (2, 2)]
    assert stats[1].min_column == 1
    assert stats[1].max_column == 2
    assert stats[1].min_row == 2
    assert stats[1].max_row == 3
    assert stats[1].min_date_created == date_created
    assert stats[1].max_date_created == datetime(2026, 1, 4, 3, 4, 5, tzinfo=UTC)
    assert stats[1].min_date_last_modified == date_last_modified
    assert stats[1].max_date_last_modified == date_last_modified


def test_build_inventory_applies_level_filter_without_counting_as_skipped():
    inventory = build_inventory(
        [
            source_object("Terrain/1/1/1"),
            source_object("Terrain/2/1/1"),
            source_object("Terrain/not-a-tile"),
        ],
        layout="auto",
        level_filter={2},
    )

    assert sorted(inventory.tiles_by_level) == [2]
    assert inventory.skipped_object_count == 1
    assert inventory.excluded_by_level_count == 1
    assert inventory.resolved_layout == "prefix/z/x/y"
    assert inventory.resolved_prefix == "Terrain/"


def test_build_inventory_skips_out_of_range_webmercator_tiles():
    inventory = build_inventory(
        [source_object("1/2/0"), source_object("1/1/1")], layout="auto", level_filter=None
    )

    assert inventory.skipped_object_count == 1
    assert inventory.total_tile_count == 1
    assert inventory.resolved_layout == "z/x/y"
    assert inventory.resolved_prefix == ""
