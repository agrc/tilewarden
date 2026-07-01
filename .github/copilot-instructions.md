# Copilot Instructions for tilewarden

Trust this file first. Only search the repo when these instructions are incomplete or when the code has clearly moved.

## Repo Summary

- `tilewarden` is a small Python CLI package that inventories tiled map objects in a Google Cloud Storage bucket and writes one GeoPackage with per-level footprint layers plus a JSON summary.
- The project is read-only with respect to GCS: it lists object metadata only. It does not download tile contents or mutate bucket state.
- Stack: Python 3.13, `google-cloud-storage`, `tqdm`, `pytest`, `ruff`, `hatchling`.
- Size/layout: one packaging config (`pyproject.toml`), one README, 8 source modules under `src/tilewarden/`, 6 test files under `tests/`, no GitHub workflows, no `Makefile`, no `tox`, no `nox`, no `pre-commit` config.

## Always-Use Setup

- Always use Python 3.13. `pyproject.toml` requires `>=3.13` and Ruff targets `py313`.
- For local agent work on this machine, assume a conda environment named `tilewarden` already exists. Activate it before running tests, Ruff, or the CLI:

```bash
conda activate tilewarden
```

- If dependencies are missing inside that environment, install the package in editable mode with dev extras before running tests or Ruff:

```bash
python -m pip install -e '.[dev]'
```

- If a clean environment is required outside the local-agent setup, create a Python 3.13 environment first:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

- Validated result: editable install succeeds in about 8 seconds on macOS and pulls `google-cloud-storage`, `tqdm`, `pytest`, and `ruff`.

## Validated Commands

Run these from the repo root.

### Test

```bash
python -m pytest
```

- Validated in the project bootstrap environment after installing dev extras.
- Result: 42 tests passed.
- Time: about 5.7 seconds wall clock.
- Tests are offline. They use fakes and `tmp_path`; they do not call GCS.

### Lint and Format Validation

```bash
ruff check .
ruff format --check .
```

- Validated in the project bootstrap environment after installing dev extras.
- `ruff check .` passed in about 0.9 seconds.
- `ruff format --check .` reported `15 files already formatted` in about 0.2 seconds.
- Use `ruff format .` only when you intend to rewrite files. For validation, prefer `--check`.

### Run / CLI Smoke Test

```bash
python -m tilewarden inventory --help
```

- Validated in the project bootstrap environment after installing dev extras.
- Works offline and prints the only supported command surface: `inventory` with `--output`, `--levels`, `--prefix`, `--layout`, `--project`, `--matrix-set webmercator`, and `--progress`.

### Live Inventory Run

```bash
python -m tilewarden inventory <bucket-name> --output <dir> [other options]
```

- This is not an offline smoke test. It hits GCS immediately through `google-cloud-storage`.
- Preconditions: network access, Application Default Credentials or other working Google auth, and a real accessible bucket.
- README-documented auth step:

```bash
gcloud auth application-default login
```

- Observed failure mode on a nonexistent bucket: `Could not list gs://...: 404 GET ... The specified bucket does not exist.`
- Cloud agents should assume real runs can also fail for missing ADC, permission errors, or API/network issues even when local tests pass.

## Recommended Validation Order

1. `python -m pip install -e '.[dev]'`
2. `python -m pytest`
3. `ruff check .`
4. `ruff format --check .`
5. `python -m tilewarden inventory --help`

If you change only pure logic or tests, steps 2 to 4 are usually sufficient. If you change CLI wiring, also run step 5.

## Architecture Map

- `pyproject.toml`: single source of package metadata, entrypoint, pytest config, and Ruff config.
- `src/tilewarden/__main__.py`: module entrypoint; calls `tilewarden.cli.main()`.
- `src/tilewarden/cli.py`: argparse definitions and top-level control flow. `run_inventory()` is the orchestration entrypoint for real behavior.
- `src/tilewarden/gcs.py`: the only GCS adapter. `list_source_objects()` wraps `google.cloud.storage.Client` and converts API failures to `GCSListingError`.
- `src/tilewarden/parsing.py`: pure parsing for `--levels` and blob-name layouts. Start here for path-format changes.
- `src/tilewarden/inventory.py`: core aggregation model. Builds `Inventory`, validates Web Mercator tile bounds, tracks skipped and excluded counts.
- `src/tilewarden/footprints.py`: Web Mercator math for tile bounds and polygon rings.
- `src/tilewarden/geopackage.py`: low-level SQLite GeoPackage writer; creates metadata tables, per-level feature tables, and rtree spatial indexes.
- `src/tilewarden/output.py`: output directory creation, GeoPackage invocation, and summary JSON generation.

## Test Map

- `tests/test_cli.py`: highest-value behavior tests for end-to-end CLI orchestration, progress behavior, summary output, and exit codes.
- `tests/test_parsing.py`: layout and level parsing matrix.
- `tests/test_inventory.py`: tile grouping, level filtering, and Web Mercator bounds filtering.
- `tests/test_output.py`: GeoPackage + summary JSON contents.
- `tests/test_gcs.py`: GCS client wiring with fakes.
- `tests/test_footprints.py`: coordinate math.

## Repo Layout Facts

- Root files/directories: `.gitignore`, `.vscode/`, `README.md`, `pyproject.toml`, `src/`, `tests/`, `output/`.
- `output/` contains local sample artifacts and is ignored by git; tests do not depend on it.
- `.vscode/settings.json` enables pytest in VS Code and prefers a conda environment manager, which matches the local `tilewarden` conda environment assumption in these instructions.
- There is no separate lint config, test config, or CI workflow outside `pyproject.toml`.

## Change Guidance

- Don't worry about making breaking changes. This is acceptable because the project is only used by our internal team and not yet released for external use.
- For parser or tile-selection changes, update the matching focused tests first or alongside code.
- For output-schema or GeoPackage changes, validate with `tests/test_output.py` and `tests/test_cli.py` before running the full suite.
- Do not assume any live GCS access is available in automation. Keep tests offline.
