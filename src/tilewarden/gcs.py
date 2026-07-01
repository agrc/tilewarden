"""Read-only Google Cloud Storage listing adapter."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from google.api_core.exceptions import GoogleAPIError
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import storage

from tilewarden.inventory import SourceObject
from tilewarden.parsing import parse_blob_name, resolve_layout, resolve_prefix

DISCOVERY_SAMPLE_SIZE = 50


@dataclass(frozen=True, slots=True)
class ListingParameters:
    layout: str
    prefix: str


class GCSListingError(RuntimeError):
    """Raised when bucket listing fails."""


def list_source_objects(
    *,
    bucket_name: str,
    prefix: str,
    layout: str,
    level_filter: set[int] | None,
    project: str | None,
) -> Iterator[SourceObject]:
    """Yield source object metadata from a GCS bucket using only list operations."""

    try:
        client = storage.Client(project=project)
        bucket = client.bucket(bucket_name)
        listing_prefixes = _listing_prefixes(
            prefix=prefix,
            layout=layout,
            level_filter=level_filter,
        )
        if listing_prefixes is None:
            yield from _source_objects_from_blobs(bucket.list_blobs(prefix=prefix or None))
            return

        for listing_prefix in listing_prefixes:
            yield from _source_objects_from_blobs(bucket.list_blobs(prefix=listing_prefix))
    except (DefaultCredentialsError, GoogleAPIError) as exc:
        raise GCSListingError(f"Could not list gs://{bucket_name}: {exc}") from exc


def discover_listing_parameters(
    *,
    bucket_name: str,
    prefix: str,
    layout: str,
    project: str | None,
    max_results: int = DISCOVERY_SAMPLE_SIZE,
) -> ListingParameters | None:
    """Infer a concrete layout and tile prefix from a bounded sample of blob names."""

    try:
        client = storage.Client(project=project)
        bucket = client.bucket(bucket_name)
        for blob in bucket.list_blobs(prefix=prefix or None, max_results=max_results):
            discovered = _discover_listing_parameters(blob.name, layout)
            if discovered is not None:
                return discovered
        return None
    except (DefaultCredentialsError, GoogleAPIError) as exc:
        raise GCSListingError(f"Could not list gs://{bucket_name}: {exc}") from exc


def _source_objects_from_blobs(blobs: Iterator[object]) -> Iterator[SourceObject]:
    for blob in blobs:
        yield SourceObject(
            name=blob.name,
            date_created=blob.time_created,
            date_last_modified=blob.updated,
        )


def _discover_listing_parameters(blob_name: str, layout: str) -> ListingParameters | None:
    if layout == "auto":
        resolved_layout = resolve_layout(blob_name, layout)
        if resolved_layout is None:
            return None
        resolved_prefix = resolve_prefix(blob_name, layout)
        if resolved_prefix is None:
            return None
        return ListingParameters(layout=resolved_layout, prefix=resolved_prefix)

    if parse_blob_name(blob_name, layout) is None:
        return None

    resolved_prefix = resolve_prefix(blob_name, layout)
    if resolved_prefix is None:
        return None
    return ListingParameters(layout=layout, prefix=resolved_prefix)


def _listing_prefixes(
    *, prefix: str, layout: str, level_filter: set[int] | None
) -> list[str] | None:
    if level_filter is None or layout == "auto":
        return None
    if layout.startswith("prefix/") and prefix == "":
        return None
    return [f"{prefix}{level}/" for level in sorted(level_filter)]
