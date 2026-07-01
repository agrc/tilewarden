"""Web Mercator tile footprint math."""

from __future__ import annotations

from tilewarden.inventory import Tile

WEBMERCATOR_WKID = 3857
WEBMERCATOR_ORIGIN_X = -20037508.342789244
WEBMERCATOR_ORIGIN_Y = 20037508.342789244
WEBMERCATOR_WORLD_WIDTH = 40075016.685578488


def webmercator_tile_ring(tile: Tile) -> list[list[float]]:
    """Return a closed EPSG:3857 polygon ring for a Web Mercator tile."""

    left, bottom, right, top = webmercator_tile_bounds(tile)

    return [
        [left, bottom],
        [left, top],
        [right, top],
        [right, bottom],
        [left, bottom],
    ]


def webmercator_tile_bounds(tile: Tile) -> tuple[float, float, float, float]:
    """Return left, bottom, right, top bounds for a Web Mercator tile."""

    matrix_size = 2**tile.level
    tile_span = WEBMERCATOR_WORLD_WIDTH / matrix_size

    left = WEBMERCATOR_ORIGIN_X + tile.column * tile_span
    right = WEBMERCATOR_ORIGIN_X + (tile.column + 1) * tile_span
    top = WEBMERCATOR_ORIGIN_Y - tile.row * tile_span
    bottom = WEBMERCATOR_ORIGIN_Y - (tile.row + 1) * tile_span

    return left, bottom, right, top
