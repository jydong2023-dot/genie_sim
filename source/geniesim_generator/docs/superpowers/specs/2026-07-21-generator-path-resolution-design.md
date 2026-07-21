# Generator Path Resolution Design

## Goal

Make scene generation independent of the checkout layout while preserving the
documented output contract. Generated USD payloads must resolve to the active
`geniesim_assets` installation, and generated scene bundles must land in the
actual `geniesim_benchmark/benchmark/config/llm_task` directory.

## Resolution Rules

### Asset root

Resolve the asset root in this order:

1. `GENIESIM_ASSETS_DIR`, when set.
2. The directory containing the imported `geniesim_assets` package.

The selected directory must contain `__init__.py`. Invalid explicit overrides
fail with a path-specific error instead of silently falling back. Asset URLs
from `ASSETS_INDEX` remain relative to this root; absolute URLs remain valid.

### Generator output root

Resolve the `llm_task` output root in this order:

1. `GENIESIM_GENERATOR_OUTPUT_DIR`, when set.
2. An importable `geniesim_benchmark` package, using its
   `benchmark/config/llm_task` directory.
3. A sibling source checkout at
   `<repo>/source/geniesim_benchmark/src/geniesim_benchmark/benchmark/config/llm_task`.

An invalid explicit override fails immediately. If automatic discovery finds
neither an installed package nor the sibling checkout, generation fails with a
message that names `GENIESIM_GENERATOR_OUTPUT_DIR` as the remedy. The generator
must not fall back to a package-local `src/benchmark` directory.

## Code Shape

Add a small path-resolution module under `geniesim_generator` with pure,
independently testable functions. `app.py` will ask it for the output root;
`utils/usd.py` will ask it for the asset root. Path resolution happens at call
time rather than import time so tests, environment overrides, and long-lived
processes observe the current configuration.

`app.py` will retain the existing `<scene_id>/<instance_number>` bundle layout.
`utils/usd.py` will retain relative payload authoring so generated scenes remain
portable when the output and asset trees are moved together or mounted at the
same expected locations.

## Errors

- Explicit paths must be expanded and resolved before validation.
- Invalid explicit paths raise `RuntimeError` containing the variable name and
  rejected path.
- Missing auto-discovery raises `RuntimeError` with the expected benchmark
  layout and override variable.
- Asset payload existence is validated before authoring. A missing indexed
  payload raises `FileNotFoundError` naming the asset URL and resolved path.

## Tests

Tests will cover:

- asset override precedence and installed-package fallback;
- rejection of an invalid asset override;
- benchmark output override precedence;
- importable benchmark resolution and sibling-checkout fallback;
- clear failure when no output target exists;
- generated payloads resolving to a real asset file;
- the direct compiler writing all five artifacts under the resolved benchmark
  output root.

The smoke test uses temporary directories and a minimal asset payload so it
does not write additional files into either source package.

## Non-Goals

- Installing `geniesim_benchmark` into the generator Conda environment.
- Moving Isaac Sim preview into the generator environment.
- Starting or configuring the Docker/Open WebUI stack.
- Changing scene DSL semantics or asset-index contents.
