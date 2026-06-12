# Phase 1 test runner

This folder contains the standalone Phase 1 TB validation suite (`test_tb.py`).

## Run locally against installed `tbsim`

```bash
python -m pytest tests/test_tb.py -v --tb=short
```

## Run locally against a branch under development

Use the helper script to clone and install a specific branch/tag/SHA from GitHub,
then run the tests against that code:

```bash
scripts/run_phase1_against_branch.sh <branch-or-sha> [owner/repo]
```

Examples:

```bash
scripts/run_phase1_against_branch.sh main
scripts/run_phase1_against_branch.sh fix-425-household-uid-filtering starsimhub/tbsim
scripts/run_phase1_against_branch.sh my-feature yourname/tbsim
```

## Run in GitHub Actions

Workflow: `.github/workflows/phase1-branch-tests.yml`

Use **Run workflow** and provide:
- `tbsim_branch`: branch/tag/SHA to test
- `tbsim_repo`: repository slug (default `starsimhub/tbsim`)
