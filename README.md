# TileWarden

`tilewarden` is a read-only CLI for inventorying tiled map objects in a Google Cloud Storage bucket and writing tile footprints to per-level GeoPackage layers.

The project targets XYZ-style Web Mercator tiles in EPSG:3857. It lists bucket objects, parses tile coordinates from object names, and writes local GeoPackage footprint files plus a JSON summary. It never uploads, deletes, rewrites, patches, or mutates bucket metadata.

## Install for development

```bash
conda create --name tilewarden python=3.13
conda activate tilewarden
pip install -e '.[dev]'
```

Run tests and linting with:

```bash
pytest
ruff format .
ruff check .
```

## Authentication

`tilewarden` uses Application Default Credentials through `google-cloud-storage`. If credentials are not already configured, run:

```bash
gcloud auth application-default login
```

You can pass `--project <project>` when the storage client should be created for a specific Google Cloud project.

## GCP Cost Awareness

Running `tilewarden` against a real Google Cloud Storage bucket can incur Google Cloud costs even though the tool is read-only. The CLI lists objects with the Cloud Storage API, and object listing requests are billed by Google Cloud as Cloud Storage operations, typically Class A operations. The exact cost depends on your bucket location, storage class, namespace type, free-tier eligibility, and current Google Cloud pricing.

The tool does not download tile object contents and does not upload, delete, rewrite, patch, or mutate bucket metadata. Its GCP usage is limited to listing object names and object metadata from the target bucket and prefix. For very large buckets, listing can require many paginated API requests, so use `--prefix` and `--levels` where practical to limit the inventory scope.

Running the local test suite does not contact Google Cloud; tests use fakes and local temporary files.

## Usage

```bash
tilewarden inventory <bucket-name> --output <directory> [--levels <levels>] [--prefix <prefix>] [--layout <layout>] [--project <project>] [--matrix-set webmercator] [--progress auto|always|never]
```

The command writes one GeoPackage footprint file named `<bucket-name>-tile-footprints.gpkg`, plus a JSON summary file named `<bucket-name>-summary.json`. Each discovered or selected level is stored as a separate GeoPackage layer named like `tile_footprints_l05`.

While running in a terminal, the CLI shows progress bars for overall progress, object listing/parsing, and GeoPackage feature writing. Use `--progress always` to force progress output when stderr is redirected, or `--progress never` to disable it. After writing output, the CLI prints the bucket, prefix, layout, matrix set, output directory, skipped object count, excluded-by-level count, total tile count, generated file count, summary JSON path, and a per-level table with tile counts and source date ranges.

## Examples

Honeycomb-style or layer-prefixed bucket objects such as `Terrain/5/10/12`:

```bash
tilewarden inventory my-tile-bucket --output ./inventory --prefix Terrain/ --layout auto
```

Unprefixed XYZ objects such as `5/10/12.png`:

```bash
tilewarden inventory my-tile-bucket --output ./inventory --layout auto
```

Explicit row-before-column objects such as `5/12/10` where the path is `z/y/x`:

```bash
tilewarden inventory my-tile-bucket --output ./inventory --layout z/y/x
```

Level ranges and mixed lists:

```bash
tilewarden inventory my-tile-bucket --output ./inventory --levels 5-7
tilewarden inventory my-tile-bucket --output ./inventory --levels 5,7,10-12
```

Prefixed listing with an explicit project:

```bash
tilewarden inventory my-tile-bucket --output ./inventory --prefix Terrain/ --project my-gcp-project
```

## Layouts

Supported layouts are:

- `auto`: parse the final three path components, tolerate an extension on the final component, and interpret them as `z/x/y`.
- `z/x/y`: objects like `5/10/12`.
- `prefix/z/x/y`: objects like `Terrain/5/10/12`.
- `z/x/y.ext`: objects like `5/10/12.png`.
- `prefix/z/x/y.ext`: objects like `Terrain/5/10/12.jpg`.
- `z/y/x`: row-before-column objects like `5/12/10`.
- `prefix/z/y/x`: prefixed row-before-column objects like `Terrain/5/12/10`.

WMTS defines `TileMatrix`, `TileRow`, and `TileCol`, but actual REST paths are service-specific. Use an explicit layout when `auto` would be ambiguous or when the object path stores row before column.

Every GeoPackage feature preserves the original `blob_name` property so later cleanup workflows can map a footprint back to the exact bucket object. Features also include the source object's GCS creation and last-modified timestamps when Cloud Storage returns them.

## Matrix Set

Only `--matrix-set webmercator` is supported in this version. It assumes Google, ArcGIS Online, and XYZ Web Mercator semantics:

- EPSG:3857 output coordinates.
- Top-left origin.
- `2 ** z` rows and columns at level `z`.
- Standard Web Mercator world extent.

This version is not correct for custom WMTS matrix sets, non-Web-Mercator tiles, bottom-left TMS row origins, unusual tile sizes, or custom scale sets.

## Output Properties

Each feature includes:

- `bucket`
- `prefix`
- `layout`
- `matrix_set`
- `level`
- `column`
- `row`
- `blob_name`
- `date_created`
- `date_last_modified`
- `wkid: 3857`

`date_created` comes from the GCS object's `time_created` metadata, and `date_last_modified` comes from the object's `updated` metadata. These fields are nullable when source metadata is unavailable. The JSON summary also includes overall and per-level min/max values for both dates. No bounds output is produced. GeoPackage output includes a spatial index for each level layer.

## Cleanup Workflows

Deletion is intentionally separate from inventory. This command only lists bucket objects and writes local files. A future cleanup workflow can compare inventory against a desired extent, write a dry-run manifest of blob names, and require a separate explicit delete command to act on that manifest.
