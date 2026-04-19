# SplitPdfByKeyWord Workflow Skill

## Purpose

This document captures the current project structure, the existing business workflows, and the standard pattern for adding a new workflow to this repository.

Use it as an implementation guide when extending the project, not as end-user documentation.

## Project Structure

The repository is organized into four layers with clear responsibilities:

- `core/`: infrastructure and runtime plumbing
- `services/`: reusable business capabilities
- `workflows/`: orchestration of one or more services
- root scripts: CLI entrypoints for a concrete use case

Current top-level layout:

- `split_pdf_keyword.py`: single-PDF split entrypoint
- `rename_pdfs_by_regex.py`: directory rename entrypoint
- `process_usb_pdfs.py`: USB import + split + rename entrypoint
- `core/config.py`: load `config.yaml`, merge `common.env`, apply runtime overrides
- `core/logging_utils.py`: initialize root logger and per-script log file
- `core/runtime.py`: force execution under `.conda/python.exe`
- `services/ocr_service.py`: OCR engine bootstrapping, CUDA self-check, page OCR
- `services/pdf_split_service.py`: split one PDF by OCR text hit rules
- `services/pdf_rename_service.py`: OCR first page and rename by regex
- `services/usb_scan_service.py`: scan removable drives, filter and copy PDFs
- `services/file_ops_service.py`: directory cleanup utilities
- `workflows/split_workflow.py`: orchestrate single PDF split
- `workflows/rename_workflow.py`: orchestrate batch rename
- `workflows/usb_batch_workflow.py`: orchestrate USB batch processing

## Layering Rules

When adding code, keep these boundaries intact:

- Entry scripts parse CLI args, ensure interpreter, load config, create logger, then call one workflow.
- Workflows coordinate steps, choose directories, pass config, and handle process-level success/failure.
- Services contain reusable logic such as OCR, splitting, renaming, scanning, and file cleanup.
- `core/` contains only shared infrastructure concerns and should stay business-agnostic.

Do not put OCR logic, PDF parsing logic, or file traversal logic directly into a root script if it can live in `services/`.

Do not make a workflow depend on a root script. Shared logic must flow downward into `workflows/`, `services/`, or `core/`.

## Existing Workflow Map

### 1. Single PDF split workflow

Entry:

- `split_pdf_keyword.py`

Execution path:

1. `ensure_project_python()` switches to `.conda/python.exe` if needed.
2. `setup_logger()` initializes console + file logging.
3. `load_runtime_config()` loads `config.yaml` and `common.env`, then applies CLI overrides.
4. Entry script maps `split_input_file` and `split_output_path` into runtime fields if CLI values were not passed.
5. `workflows.split_workflow.process_pdf_with_config()` executes the split flow.
6. Workflow optionally clears output directory.
7. Workflow runs OCR startup self-check and builds OCR processor.
8. Workflow OCRs all pages.
9. Workflow creates `PDFSplitter` and exports split PDFs.

Core characteristics:

- Single input file
- Optional output cleanup before processing
- Full-document OCR before splitting
- Split rule is based on a page containing all configured `split_keywords`
- A page is excluded as a split point if it also contains any `not_split_keywords`

### 2. Rename workflow

Entry:

- `rename_pdfs_by_regex.py`

Execution path:

1. `ensure_project_python()`
2. `setup_logger()`
3. `load_config()` reads config and env substitutions
4. Entry script resolves `rename_input_path`
5. `workflows.rename_workflow.rename_pdfs()` collects target PDFs
6. Workflow delegates to `services.pdf_rename_service.rename_pdf_files()`
7. Service runs OCR self-check once, OCRs the first page of each PDF, extracts a regex match, sanitizes the filename, and renames or copies the file

Core characteristics:

- Directory-based batch operation
- OCR only on first page
- Regex-driven naming
- Supports in-place rename or copy-to-output mode

### 3. USB batch workflow

Entry:

- `process_usb_pdfs.py`

Execution path:

1. `ensure_project_python()`
2. `setup_logger()`
3. `load_runtime_config()`
4. `workflows.usb_batch_workflow.run_usb_batch()` starts batch processing
5. Workflow discovers removable drives via `services.usb_scan_service.list_removable_drive_roots()`
6. Workflow copies matching PDFs into local `input_path`
7. Workflow clears shared output directory once
8. Workflow loops through each copied PDF
9. For each file, workflow reuses `process_pdf_with_config(..., clear_output=False)` to append split outputs into the same output directory
10. Workflow detects only the newly generated PDFs for that source file
11. Workflow renames those new PDFs via `rename_pdf_files()`

Core characteristics:

- Windows-only USB discovery
- Date-filtered PDF import
- Shared local staging directory
- Reuse of existing split and rename services instead of reimplementing them

## Current Configuration Model

The configuration comes from two sources:

- `config.yaml`: rule-like configuration
- `common.env`: environment-specific values

Patterns already used in this project:

- Runtime path values in YAML can reference env variables like `${INPUT_PATH:-./input/}`.
- Entry scripts may override config with CLI arguments.
- Workflow-specific aliases exist:
  - `split_input_file`
  - `split_output_path`
  - `rename_input_path`
- Service-level rules live under semantic keys:
  - `ocr.use_gpu`
  - `ocr.split_keywords`
  - `ocr.not_split_keywords`
  - `regex_pattern`

When adding a new workflow, prefer this model:

- Put environment-sensitive paths or toggles in `common.env`.
- Put business rules and defaults in `config.yaml`.
- Let the entry script apply final runtime overrides from CLI args.

## Reusable Building Blocks

These are the main reusable units to compose new workflows:

- `load_runtime_config()`: standard config loading with runtime overrides
- `setup_logger()`: standard per-entry logging
- `ensure_project_python()`: standard interpreter guard
- `run_startup_self_check()`: initialize OCR and log provider state
- `PDFOCRProcessor.process_pdf()`: OCR all pages of one PDF
- `PDFSplitter.split_by_ocr_results()`: split PDF from precomputed OCR results
- `rename_pdf_files()`: OCR-first-page rename for a PDF list
- `copy_pdfs_from_usb_drives()`: import source PDFs from removable drives
- `clear_directory()` / `clear_output_directory()`: cleanup approved working directories

Preferred reuse principle:

- If the logic already exists as a service, call it from the new workflow.
- If two workflows need the same new behavior, add or extend a service.
- Only create a new root script when the user needs a new CLI entrypoint.

## Standard Pattern For Adding A New Workflow

### Step 1. Define the use case

Clarify:

- Input source: single PDF, local directory, USB, or another source
- Processing stages: OCR, split, rename, copy, filter, archive, export
- Output form: renamed files, split files, report, staging directory
- Cleanup behavior: whether to clear input/output directories
- Reusability: which steps can be delegated to existing services

### Step 2. Decide whether a new service is required

Create a new service only when the behavior is reusable or domain-specific, for example:

- new file discovery logic
- new OCR post-processing logic
- new output naming logic
- new export logic

Keep the workflow thin if it mostly sequences existing services.

### Step 3. Add the workflow module

Create a new file under `workflows/`, for example `workflows/my_new_workflow.py`.

The workflow should:

- accept `config` and `logger`
- validate required inputs early
- resolve runtime directories and paths
- call services in the intended order
- return `True` or `False` for operational success
- log summary information and per-file failures

Recommended skeleton:

```python
from pathlib import Path


def run_my_new_workflow(config, logger):
    input_path = Path(config.get("input_path", "./input/"))
    output_path = Path(config.get("output_path", "./output/"))

    if not input_path.exists():
        logger.error(f"输入目录不存在: {input_path}")
        return False

    success_count = 0
    failed_items = []

    for item in sorted(input_path.glob("*.pdf")):
        try:
            # call existing services here
            success_count += 1
        except Exception as exc:
            failed_items.append(str(item))
            logger.exception(f"处理失败: {item}, error={exc}")

    logger.info(f"流程结束：成功 {success_count} 个，失败 {len(failed_items)} 个。")
    if failed_items:
        logger.warning("失败列表: " + " | ".join(failed_items))

    return success_count > 0
```

### Step 4. Add a root entrypoint only if needed

Create a new root script when the workflow should be runnable directly by users.

Entry script pattern:

1. parse CLI args
2. call `ensure_project_python()`
3. call `setup_logger()`
4. load config
5. map workflow-specific config aliases if needed
6. call the workflow

Recommended skeleton:

```python
import argparse

from core.config import load_runtime_config
from core.logging_utils import setup_logger
from core.runtime import ensure_project_python
from workflows.my_new_workflow import run_my_new_workflow


def parse_args():
    parser = argparse.ArgumentParser(description="新工作流说明。")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--env", default=None)
    return parser.parse_args()


def main():
    ensure_project_python()

    logger = setup_logger()
    args = parse_args()

    try:
        config = load_runtime_config(config_path=args.config, env_path=args.env)
    except (FileNotFoundError, ValueError) as exc:
        logger.error(str(exc))
        return

    run_my_new_workflow(config, logger)


if __name__ == "__main__":
    main()
```

### Step 5. Extend configuration carefully

When introducing new config:

- Reuse existing top-level names only if the semantics match.
- Prefer names scoped by use case, such as `archive_input_path`, `archive_output_path`, `archive_rules`.
- Keep default values explicit in `config.yaml`.
- Use `${VAR:-default}` for environment-dependent paths.

### Step 6. Keep logging behavior consistent

Follow the existing logging style:

- log start and end of major stages
- log important resolved paths
- log counts of processed files
- log warnings for skipped items
- use `logger.exception(...)` inside per-file failure handling

Do not create ad hoc logging systems or bypass `setup_logger()`.

## Workflow Design Constraints In This Repo

### 1. Respect destructive operations

This codebase intentionally clears working directories in some workflows.

Before adding cleanup logic:

- use `services.file_ops_service`
- only clear dedicated working directories
- do not clear user source directories unless the workflow explicitly requires it

### 2. Reuse OCR initialization efficiently

OCR startup is expensive. If a workflow processes many PDFs in one batch:

- initialize OCR once when possible
- avoid repeating startup self-check per file unless the current service API forces it

Note:

- `rename_pdf_files()` already initializes OCR once for the file batch it receives.
- `process_pdf_with_config()` initializes OCR per invocation because it is designed around a single input document.

### 3. Keep workflows orchestration-focused

If a workflow grows to contain detailed OCR matching, regex extraction, or directory cleanup internals, move that logic into a service.

### 4. Preserve current success/failure contract

The project currently uses a pragmatic boolean contract:

- `True`: workflow completed with at least one meaningful success
- `False`: validation failed, nothing processed, or the run was operationally unsuccessful

Stay aligned with that unless there is a strong reason to introduce richer result objects.

## Recommended Checklist For A New Workflow

- Identify whether an existing service already covers each step.
- Add a new service only for reusable domain logic.
- Add a workflow under `workflows/` to orchestrate the steps.
- Add a root script only if direct CLI execution is needed.
- Extend `config.yaml` and `common.env` using the existing template style.
- Reuse `ensure_project_python()`, `setup_logger()`, and `load_runtime_config()`.
- Return boolean success from the workflow.
- Log stage boundaries, resolved paths, counts, and failures.
- Keep destructive cleanup limited to dedicated workspace directories.

## Suggested Naming Conventions

- Workflow module: `workflows/<verb>_<target>_workflow.py`
- Workflow function: `run_<verb>_<target>()` or `<verb>_<target>()`
- Service module: `services/<capability>_service.py`
- Root script: `<verb>_<target>.py` when it represents a user-facing action
- Config aliases: `<workflow>_input_path`, `<workflow>_output_path`, `<workflow>_rules`

## What To Reuse First

When implementing a new workflow in this repository, try this order:

1. Reuse `core` helpers for runtime, config, and logging.
2. Reuse existing `services` for OCR, split, rename, cleanup, and source discovery.
3. Add a thin workflow that sequences those services.
4. Add or extend services only when orchestration alone is not enough.
5. Add a new CLI entry script only if the workflow must be directly runnable.

## Anti-Patterns To Avoid

- Putting business logic directly in a root script
- Making a workflow import another root script
- Duplicating OCR startup code outside `services/ocr_service.py`
- Reimplementing file cleanup instead of using `services/file_ops_service.py`
- Embedding hard-coded absolute paths in workflow code
- Modifying user source files when a copy-to-output mode is safer and sufficient

## Summary

This project already follows a useful pattern:

- root scripts define execution scenarios
- workflows orchestrate
- services implement capabilities
- core provides shared infrastructure

A new workflow should preserve that structure. Build the new use case by composing existing services first, extracting only truly reusable new behavior into `services/`, and keeping the entry script minimal.
