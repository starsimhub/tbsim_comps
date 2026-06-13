# Validation tests

| File | Scope |
|------|-------|
| `test_sim.py` | Full `tbsim.Sim` integration — end-to-end runs, result oracles, reproducibility |
| `test_sim_endemic.py` | Endemic TB with Tx/TPT — clearance, reinfection, golden prevalence trajectory |
| `test_tb.py` | TB module unit/integration checks (state machine, rates, reinfection indexes) |
| `test_tbsim_regressions.py` | **Upstream bug regressions** (TBUG-001 … TBUG-004); fail until fixed |

Upstream bug documentation lives in `findings/` (see `findings/README.md`).

## Install and run

```bash
pip install -r requirements.txt
python -m pytest tests/ -v --tb=short
```

## Upstream bug workflow

```bash
scripts/report_tbsim_bugs.sh
```

1. Script prints open **TBUG-xxx** entries from `findings/bug_registry.py` and runs regression tests.
2. Copy failing test + `findings/TBSIM_KNOWN_BUGS.md` entry into a `starsimhub/tbsim` GitHub issue.
3. When fixed upstream, set `status: fixed` in `findings/bug_registry.py` and confirm the test passes.

## Run against a branch under development

```bash
scripts/run_phase1_against_branch.sh <branch-or-sha> [owner/repo]
```

## GitHub Actions

Workflow: `.github/workflows/validation-tests.yml`

Use **Run workflow** and provide `tbsim_branch` and `tbsim_repo`.
