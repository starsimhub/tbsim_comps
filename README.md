# tbsim_comps validation harness

> Note: Implementation of the tests is in progress

This repository contains an external test harness for validating `tbsim` from source branches, tags, or SHAs.

The key goal is to run tests against the exact development version of `tbsim` you choose, rather than whatever is currently on `main`.

## Repository layout

- `tbsim/`  
  Reference checkout of the upstream package. Treat as read-only in this harness.
- `tests/`  
  Validation tests executed by this harness (for example `tests/test_tb.py`).
- `scripts/run_phase1_against_branch.sh`  
  Local helper to clone/install a target branch and run tests.
- `.github/workflows/phase1-branch-tests.yml`  
  GitHub Actions workflow to run the same branch-based test flow in CI.

## Prerequisites

- Python 3.11+ (3.12 recommended)
- `pip`
- `git`
- Internet access (for cloning target repositories/branches)

## Quick start (local)

Run the test suite currently in `tests/` using your current environment:

```bash
python -m pytest tests/test_tb.py -v --tb=short
```

## Run tests against a specific branch

Use the helper script to test a branch, tag, or SHA from `starsimhub/tbsim` (or a fork):

```bash
scripts/run_phase1_against_branch.sh <branch-or-sha> [owner/repo]
```

Examples:

```bash
scripts/run_phase1_against_branch.sh main
scripts/run_phase1_against_branch.sh fix-uid starsimhub/tbsim
scripts/run_phase1_against_branch.sh my-feature yourname/tbsim
```

What the script does:

1. Clones the selected ref into `.tmp/tbsim-src`
2. Installs `tbsim` editable from that clone
3. Prints the import path so you can confirm which source is under test
4. Runs the test suite from `tests/`

## Run in GitHub Actions

Workflow file:

- `.github/workflows/phase1-branch-tests.yml`

How to run:

1. Open **Actions** in GitHub
2. Select **Phase 1 TB tests against tbsim branch**
3. Click **Run workflow**
4. Fill inputs:
   - `tbsim_branch`: branch, tag, or SHA to test
   - `tbsim_repo`: repo slug, default `starsimhub/tbsim`
5. Start the run and review logs/artifacts

The workflow installs `tbsim` from the selected ref and runs the local harness tests against that installed version.

## Why the runner uses a temp directory

Python import resolution can accidentally pick up the local reference checkout (`./tbsim`) instead of the installed target package.

To avoid false results, both local and CI runners execute pytest from a temporary directory and pass the test file path explicitly.

## Common commands

Run branch-based validation locally:

```bash
scripts/run_phase1_against_branch.sh feature-branch starsimhub/tbsim
```

Run direct pytest locally:

```bash
python -m pytest tests/test_tb.py -v --tb=short
```

Show which `tbsim` is currently imported:

```bash
python -c "import tbsim; print(tbsim.__file__)"
```

## Troubleshooting

### Import mismatch (wrong package under test)

If the printed path does not point to `.tmp/tbsim-src/tbsim/__init__.py`, your environment may still be using a previously installed package.

Re-run:

```bash
scripts/run_phase1_against_branch.sh <branch-or-sha> [owner/repo]
```

### Branch not found

Verify the branch/repo combination exists:

```bash
git ls-remote --heads https://github.com/<owner>/<repo>.git
```

### Dependency install issues

Upgrade pip and retry:

```bash
python -m pip install --upgrade pip
```

## Extending this harness

To add more tests, place new files under `tests/` and include them in your pytest command/workflow run step.

Keep test code in this repository so it can validate multiple `tbsim` branches without modifying upstream source.
