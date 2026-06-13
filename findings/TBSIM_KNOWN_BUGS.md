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
| TBUG-005 | high | `test_dx_delivery_requires_hsb_sought_care_by_default` | open |
| TBUG-006 | medium | `test_dx_product_administer_works_after_product_initialization` | open |
| TBUG-007 | medium | `test_tx_product_administer_works_after_product_initialization` | open |
| TBUG-008 | medium | `test_xpert_prior_tb_history_strata_are_explicit` | open |
| TBUG-009 | medium | `test_dr_tb_secondline_outputs_are_separable` | open |

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

## TBUG-005 — `DxDelivery` tests all alive agents when HSB is absent

**Symptom:** A default `DxDelivery(CAD(), coverage=1.0)` without `HealthSeekingBehavior` tests every alive agent each step. This breaks the care-cascade assumption in Phase 2: without `sought_care`, default diagnosis delivery should not occur.

**Expected:** Default eligibility should require `sought_care`, or fail loudly when HSB is missing. Mass screening should require explicit custom eligibility.

**Repro:**

```python
import starsim as ss
import tbsim

sim = tbsim.Sim(
    sim_pars=dict(n_agents=50, stop=ss.date("2000-02-01"), dt=ss.days(7)),
    tb_pars=dict(beta=ss.peryear(0), init_prev=ss.bernoulli(0)),
    pars=dict(interventions=[tbsim.DxDelivery(tbsim.CAD(), coverage=1.0)]),
)
sim.run()
dx = next(iter(sim.interventions.values()))
assert sum(dx.results.n_tested) == 0
```

---

## TBUG-006 — Diagnostic products cannot be administered in isolation after init

**Symptom:** `Xpert().administer(sim, uids)` raises `DistNotInitializedError` after standard `init_pre/init_post` product initialization because the internal `choice2d` distribution is not initialized.

**Expected:** Diagnostic products should be unit-testable via `administer()` after normal product initialization, or expose a documented initialization helper.

**Repro:** Initialize a small `tbsim.Sim`, then call:

```python
product = tbsim.Xpert()
product.init_pre(sim)
product.init_post()
product.administer(sim, uids)
```

---

## TBUG-007 — Treatment products cannot be administered in isolation after init

**Symptom:** `DOTS().administer(sim, uids)` raises `DistNotInitializedError` after standard `init_pre/init_post` product initialization because internal Bernoulli distributions are not initialized.

**Expected:** Treatment products should be unit-testable via `administer()` after normal product initialization, or expose a documented initialization helper.

**Repro:** Initialize a small `tbsim.Sim`, then call:

```python
product = tbsim.DOTS()
product.init_pre(sim)
product.init_post()
product.administer(sim, uids)
```

---

## TBUG-008 — Xpert scenarios lack prior-TB-history stratification

**Symptom:** `Xpert` probability tables stratify by age and TB state, but not by prior TB, recent prior TB, or previous treatment history. This makes prior-TB diagnostic scenario assumptions silent.

**Expected:** Prior-treatment-history scenarios should expose an explicit table dimension, scenario flag, or documented limitation so repeated diagnosis workflows do not overclaim specificity/sensitivity behavior.

**Repro:**

```python
import tbsim

assert "prior_tb" in tbsim.Xpert().df.columns
```

---

## TBUG-009 — DR-TB second-line outputs are not separable

**Symptom:** `SecondLine` treatment can be delivered, but outcomes are reported through generic `TxDelivery` result channels (`n_treated`, `n_success`, `n_failure`, etc.) with no DR/MDR/resistance-specific output or state.

**Expected:** Drug-resistant TB scenarios should require explicit assumptions and produce separable outputs, so DR and drug-susceptible pathways are not conflated.

**Repro:** Run `TxDelivery(SecondLine())` and inspect `tx.results.keys()`; no DR/MDR/resistance-specific channel is present.

---

## Team workflow

```bash
# Print registry + run regression tests (failures = open bugs)
scripts/report_tbsim_bugs.sh

# Full harness (passing checks + known upstream failures)
python -m pytest tests/ -v --tb=short

# Only regression file
python -m pytest tests/test_tbsim_regressions.py -v
```

When filing a GitHub issue on `starsimhub/tbsim`, use the **TBUG-xxx** ID in the title and link to the failing test name.
