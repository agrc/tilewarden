"""Read-only Google Cloud Storage listing adapter."""

from __future__ import annotations

from collections.abc import Iterator

from google.api_core.exceptions import GoogleAPIError
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import storage

from tilewarden.inventory import SourceObject


class GCSListingError(RuntimeError):
    """Raised when bucket listing fails."""


def list_source_objects(
    *, bucket_name: str, prefix: str, project: str | None
) -> Iterator[SourceObject]:
    """Yield source object metadata from a GCS bucket using only list operations."""

    try:
        client = storage.Client(project=project)
        bucket = client.bucket(bucket_name)
        for blob in bucket.list_blobs(prefix=prefix or None):
            yield SourceObject(
                name=blob.name,
                date_created=blob.time_created,
                date_last_modified=blob.updated,
            )
    except (DefaultCredentialsError, GoogleAPIError) as exc:
        raise GCSListingError(f"Could not list gs://{bucket_name}: {exc}") from exc
