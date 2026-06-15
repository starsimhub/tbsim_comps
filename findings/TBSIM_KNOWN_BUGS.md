# Known upstream tbsim bugs (open)

Tracked by `tests/test_tbsim_regressions.py`. Each row is one scripted defect to
file with the tbsim team. When a bug is fixed upstream, update `findings/bug_registry.py`
(`status` → `fixed`) and confirm the matching test passes.

| ID | Severity | Test | Status |
|----|----------|------|--------|
| TBUG-001 | high | `test_dur_reinfection_protection_accepts_ss_years` | open |
| TBUG-005 | high | `test_dx_delivery_requires_hsb_sought_care_by_default` | open |
| TBUG-006 | medium | `test_dx_product_administer_works_after_product_initialization` | open |
| TBUG-007 | medium | `test_tx_product_administer_works_after_product_initialization` | open |

## TBUG-001 — `dur_reinfection_protection` duration input crashes mid-run

**Symptom:** `dur_reinfection_protection=ss.years(2)` raises `AttributeError: 'years' object has no attribute 'rvs'` during `TB.step()`.

**Expected:** Either accept bare Starsim durations or validate at init with a clear error naming `dur_reinfection_protection`.

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
