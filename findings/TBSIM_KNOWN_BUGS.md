# Known upstream tbsim bugs (open)

Tracked by `tests/test_tbsim_regressions.py`. Each row is one scripted defect to
file with the tbsim team. When a bug is fixed upstream, update `findings/bug_registry.py`
(`status` → `fixed`) and confirm the matching test passes.

| ID | Severity | Test | Status |
|----|----------|------|--------|
| TBUG-001 | high | `test_dur_reinfection_protection_accepts_ss_years` | open |
| TBUG-002 | medium | `test_sum_all_tb_states_equals_alive_population` | open |
| TBUG-003 | medium | `test_treatment_without_tx_delivery_agents_not_stuck` | open |
| TBUG-004 | low | `test_reinfection_protection_skipped_when_rr_cleared_is_one` | open |

## TBUG-001 — `dur_reinfection_protection` crashes on `ss.years()`

**Symptom:** `dur_reinfection_protection=ss.years(2)` raises `AttributeError: 'years' object has no attribute 'rvs'` during `TB.step()`.

**Expected:** Accept bare Starsim durations or validate at init with a clear error.

**Repro:**

```python
import starsim as ss
import tbsim

tbsim.Sim(tb_pars=dict(
    dur_reinfection_protection=ss.years(2),
    init_prev=ss.bernoulli(0.25),
    beta=ss.peryear(0.2),
)).run()
```

**Workaround:** `dur_reinfection_protection=ss.constant(v=ss.years(2))`

---

## TBUG-002 — Per-state counts do not partition alive population

**Symptom:** `sum(n_{state} for state in TBS) > n_alive` whenever `n_DEAD > 0` (e.g. 221/627 timesteps with TB mortality). Living states sum to `n_alive` correctly; `n_DEAD` includes agents with `alive=False` still in the results stock.

**Expected:** Results either exclude non-alive terminal agents from `n_DEAD`, or document that only non-terminal states partition `n_alive`.

**Repro:** `tbsim.Sim` with `sym_dead=ss.peryear(0.8)`, compare `sum(tb.results[f'n_{s.name}'][ti])` to `sim.results.n_alive[ti]`.

---

## TBUG-003 — `TREATMENT` state permanent without `TxDelivery`

**Symptom:** Agents in `TREATMENT` never transition out if no `TxDelivery` intervention is present (acknowledged in `tb.py` comment but no guard).

**Expected:** Natural-history exit, startup validation, or explicit API error when `TREATMENT` is used without `TxDelivery`.

**Repro:** After `sim.init()`, set `tb.state[uids] = TBS.TREATMENT`; run 10 years without `TxDelivery`.

---

## TBUG-004 — No-op reinfection protection when `rr_reinfection_cleared=1.0`

**Symptom:** INFECTION→CLEARED schedules finite `ti_rr_reinfection_wane` even when `rr_reinfection_cleared=1.0`, so protection windows have no effect.

**Expected:** Skip scheduling when `rr_reinfection_cleared >= 1.0`, or change the default when `dur_reinfection_protection` is set.

**Repro:** Force INFECTION→CLEARED with `dur_reinfection_protection=ss.constant(v=365)` and default `rr_reinfection_cleared`.

---

## Team workflow

```bash
# Print registry + run regression tests (failures = open bugs)
scripts/report_tbsim_bugs.sh

# Full harness (45 pass + 4 known upstream failures)
python -m pytest tests/ -v --tb=short

# Only regression file
python -m pytest tests/test_tbsim_regressions.py -v
```

When filing a GitHub issue on `starsimhub/tbsim`, use the **TBUG-xxx** ID in the title and link to the failing test name.
