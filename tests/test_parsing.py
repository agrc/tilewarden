import pytest

from tilewarden.parsing import (
    LayoutParseError,
    LevelParseError,
    parse_blob_name,
    parse_level_filter,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("5", {5}),
        ("5-7", {5, 6, 7}),
        ("5,7,10-12", {5, 7, 10, 11, 12}),
        ("5,5,6", {5, 6}),
    ],
)
def test_parse_level_filter(value, expected):
    assert parse_level_filter(value) == expected


@pytest.mark.parametrize("value", ["a", "5-", "-7", "7-5", "5,,6", "5.1"])
def test_parse_level_filter_rejects_invalid_input(value):
    with pytest.raises(LevelParseError):
        parse_level_filter(value)


@pytest.mark.parametrize(
    ("blob_name", "layout", "expected"),
    [
        ("5/10/12", "z/x/y", (5, 10, 12)),
        ("Terrain/5/10/12", "prefix/z/x/y", (5, 10, 12)),
        ("5/10/12.png", "z/x/y.ext", (5, 10, 12)),
        ("Terrain/5/10/12.jpg", "prefix/z/x/y.ext", (5, 10, 12)),
        ("5/12/10", "z/y/x", (5, 10, 12)),
        ("Terrain/5/12/10", "prefix/z/y/x", (5, 10, 12)),
    ],
)
def test_parse_blob_name_explicit_layouts(blob_name, layout, expected):
    parsed = parse_blob_name(blob_name, layout)

    assert parsed is not None
    assert (parsed.level, parsed.column, parsed.row) == expected
    assert parsed.blob_name == blob_name


@pytest.mark.parametrize(
    ("blob_name", "expected"),
    [
        ("Terrain/5/10/12", (5, 10, 12)),
        ("5/10/12", (5, 10, 12)),
        ("Terrain/5/10/12.png", (5, 10, 12)),
        ("archive/Terrain/5/10/12.jpg", (5, 10, 12)),
    ],
)
def test_parse_blob_name_auto_uses_final_three_components(blob_name, expected):
    parsed = parse_blob_name(blob_name)

    assert parsed is not None
    assert (parsed.level, parsed.column, parsed.row) == expected


@pytest.mark.parametrize(
    ("blob_name", "layout"),
    [
        ("metadata.json", "auto"),
        ("Terrain/metadata.json", "auto"),
        ("Terrain/5/10/12", "z/x/y"),
        ("5/10/not-a-row", "z/x/y"),
    ],
)
def test_parse_blob_name_returns_none_for_non_tile_objects(blob_name, layout):
    assert parse_blob_name(blob_name, layout) is None


def test_parse_blob_name_rejects_unknown_layout():
    with pytest.raises(LayoutParseError):
        parse_blob_name("5/10/12", "wmts")
