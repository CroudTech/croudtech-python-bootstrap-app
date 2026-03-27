# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`croudtech-bootstrap` is a CLI tool for pushing and pulling application configuration (secrets, S3 config, SSM parameters) to/from AWS services. It uses AWS S3 for config storage, AWS SSM Parameter Store for parameters, and AWS Secrets Manager for secrets. It also manages Redis database allocation across environments/apps.

## Build & Development

- **Package manager**: Poetry (`pyproject.toml`)
- **Python**: >=3.9, <3.14
- **Install deps**: `poetry install`
- **CLI entry point**: `croudtech-bootstrap` (mapped to `croudtech_bootstrap_app.cli:cli`)

## Testing

- **Run all tests**: `py.test --disable-warnings` or `make test`
- **Run a single test**: `py.test croudtech_bootstrap_app/tests/bootstrap_test.py::test_manager`
- **Test config**: `setup.cfg` under `[tool:pytest]` — test discovery looks in `croudtech_bootstrap_app/` for files matching `test_*.py`, `tests/*.py`, `tests.py`
- **Test fixtures**: Tests use local YAML files in `croudtech_bootstrap_app/tests/test_values/` to test config parsing without AWS

## Linting

- **Flake8**: `flake8` (config in `setup.cfg` — ignores E203, E501, W503; max line length 88)
- **isort**: `isort --recursive --check-only -p . --diff` (fix with `isort --recursive -p .`)
- **Black**: configured at line length 88
- **Run all quality checks**: `make quality`

## Architecture

The core domain is in `croudtech_bootstrap_app/bootstrap.py` with four main classes:

- **`BootstrapManager`** — Top-level orchestrator. Holds AWS clients (S3, SSM, Secrets Manager), discovers environments from a directory structure, and coordinates push/pull/cleanup operations.
- **`BootstrapEnvironment`** — Represents a single environment (e.g., staging, production). Discovered from subdirectories of the values path. Contains multiple `BootstrapApp` instances.
- **`BootstrapApp`** — Represents one application's config within an environment. Handles reading local YAML files (`.yaml` for params, `.secret.yaml` for secrets), uploading to S3, pushing to SSM/Secrets Manager, fetching remote values, and cleaning up orphaned parameters/secrets.
- **`BootstrapParameters`** — Facade for pulling config. Merges app-specific and common params, handles Redis DB auto-allocation, and formats output as env vars.

**CLI** (`cli.py`): Click-based CLI with commands `init`, `get-config`, `put-config`, `cleanup-secrets`, `list-apps`, and a `manage-redis` subgroup (`show-db`, `show-dbs`, `allocate-db`, `deallocate-db`).

**Redis allocation** (`redis_config.py`): Uses Redis DB 15 as a config database to track which DB index (0-14) is allocated to which app/environment combination.

**Config file convention**: Values directories contain per-environment subdirectories, each with `<AppName>.yaml`, `<AppName>.secret.yaml`, `common.yaml`, and `common.secret.yaml`. Nested YAML keys are flattened with `_` separators.

## Key Details

- Default AWS region is `eu-west-2`
- `AWS_ENDPOINT_URL` env var overrides AWS endpoints (for local testing with LocalStack etc.)
- S3 bucket naming convention: `app-bootstrap-{AWS_ACCOUNT_ID}`
- Log level controlled by `LOG_LEVEL` env var (defaults to CRITICAL)
- Empty secret values are stored as `__EMPTY__` in Secrets Manager and converted back on retrieval
- SSM parameters larger than 4096 bytes or empty are skipped during push
- Retry logic uses exponential backoff for AWS API throttling
