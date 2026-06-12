# tbsim_comps validation harness

This repository contains an external test harness for validating `tbsim` from source branches, tags, or SHAs.

Install the target `tbsim` version with `requirements.txt`, then run integration and unit tests that exercise the full `tbsim.Sim` API and TB module behavior.

## Repository layout

- `tbsim/`  
  Reference checkout of the upstream package. Treat as read-only in this harness.
- `tests/`  
  Validation tests (`tests/test_sim.py` for full Sim runs, `tests/test_tb.py` for TB module checks).
- `requirements.txt`  
  Pins `tbsim` to a Git ref plus pytest dependencies.
- `scripts/run_tests.sh`  
  Install from `requirements.txt` and run the full suite.
- `scripts/run_phase1_against_branch.sh`  
  Install a specific branch via pip and run tests.
- `.github/workflows/phase1-branch-tests.yml`  
  GitHub Actions workflow to run the same branch-based test flow in CI.

## Prerequisites

- Python 3.11+ (3.12 recommended)
- `pip`
- `git`
- Internet access (for cloning target repositories/branches)

## Quick start (local)

Install dependencies and run the full suite:

```bash
scripts/run_tests.sh
```

Or, if you have already installed from `requirements.txt`:

```bash
python -m pytest tests/ -v --tb=short
```

Confirm which `tbsim` package is imported:

```bash
python -c "import tbsim; print(tbsim.__file__)"
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

1. Installs `tbsim` from the selected Git ref via pip
2. Prints the import path so you can confirm which source is under test
3. Runs the test suite from `tests/`

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

## Import shadowing

If a local reference checkout exists at `./tbsim/`, Python may import that folder instead of the pip-installed package. Always check `tbsim.__file__` before trusting results.

## Common commands

Install and run everything:

```bash
scripts/run_tests.sh
```

Run only Sim integration tests:

```bash
python -m pytest tests/test_sim.py -v --tb=short
```

Run branch-based validation:

```bash
scripts/run_phase1_against_branch.sh feature-branch starsimhub/tbsim
```

## Troubleshooting

### Import mismatch (wrong package under test)

If the printed path points at `./tbsim/` in this repo, or an unexpected site-packages path, reinstall:

```bash
pip install -r requirements.txt --force-reinstall
```

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
