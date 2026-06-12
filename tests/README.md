# Validation tests

| File | Scope |
|------|-------|
| `test_sim.py` | Full `tbsim.Sim` integration — end-to-end runs, result oracles, reproducibility |
| `test_sim_endemic.py` | Endemic TB with Tx/TPT — clearance, reinfection, golden prevalence trajectory |
| `test_tb.py` | TB module unit/integration checks (state machine, rates, reinfection indexes) |
| `test_tbsim_regressions.py` | Known upstream tbsim bugs — fail until fixed |

## Install and run

```bash
pip install -r requirements.txt
python -m pytest tests/ -v --tb=short
```

Or use the helper:

```bash
scripts/run_tests.sh
```

## Run against a branch under development

```bash
scripts/run_phase1_against_branch.sh <branch-or-sha> [owner/repo]
```

## GitHub Actions

Workflow: `.github/workflows/phase1-branch-tests.yml`

Use **Run workflow** and provide `tbsim_branch` and `tbsim_repo`.
