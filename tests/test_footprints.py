from tilewarden.footprints import (
    WEBMERCATOR_ORIGIN_X,
    WEBMERCATOR_ORIGIN_Y,
    webmercator_tile_bounds,
    webmercator_tile_ring,
)
from tilewarden.inventory import Tile


def tile(*, level, column, row, blob_name):
    return Tile(
        level=level,
        column=column,
        row=row,
        blob_name=blob_name,
        date_created=None,
        date_last_modified=None,
    )


def test_webmercator_tile_ring_for_world_tile():
    ring = webmercator_tile_ring(tile(level=0, column=0, row=0, blob_name="0/0/0"))

    assert ring == [
        [WEBMERCATOR_ORIGIN_X, -WEBMERCATOR_ORIGIN_Y],
        [WEBMERCATOR_ORIGIN_X, WEBMERCATOR_ORIGIN_Y],
        [WEBMERCATOR_ORIGIN_Y, WEBMERCATOR_ORIGIN_Y],
        [WEBMERCATOR_ORIGIN_Y, -WEBMERCATOR_ORIGIN_Y],
        [WEBMERCATOR_ORIGIN_X, -WEBMERCATOR_ORIGIN_Y],
    ]


def test_webmercator_tile_ring_for_zoom_one_lower_right():
    ring = webmercator_tile_ring(tile(level=1, column=1, row=1, blob_name="1/1/1"))

    assert ring == [
        [0.0, -20037508.342789244],
        [0.0, 0.0],
        [20037508.342789244, 0.0],
        [20037508.342789244, -20037508.342789244],
        [0.0, -20037508.342789244],
    ]


def test_webmercator_tile_bounds_for_zoom_one_lower_right():
    bounds = webmercator_tile_bounds(tile(level=1, column=1, row=1, blob_name="1/1/1"))

    assert bounds == (0.0, -20037508.342789244, 20037508.342789244, 0.0)
