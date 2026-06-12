# tbsim Package Validation Plan

## Overview

This document describes the validation strategy for the tbsim package. The goal is to provide enough test coverage to catch regressions, verify correctness of the epidemiological model, and ensure that new features integrate cleanly with existing components. The plan is organized into phases that build on each other, starting from the smallest testable units and working up through integration, combinatorial, and performance layers.

The structure draws from the commit history, which shows that the most fragile areas of the codebase have been the UID/agent indexing logic (bug #425, fixed in v0.8.1), the household-aware filtering in migration and TPT delivery, and the multi-step cascade chains between health-seeking, diagnostics, and treatment. 

---

## Evidence-Based Feature Mapping and Combination Matrix

This section maps evidence-backed TB program features (WHO and other major public health guidance) to tbsim features and planned automated tests. The intent is to avoid building a test suite that is internally consistent but externally misaligned with real TB epidemiology and policy use-cases.

### A. Feature Mapping: Guidance -> Model Feature -> Test Coverage

| Evidence-backed feature area | Representative guidance source | tbsim feature status | Existing planned test coverage | Coverage status |
|---|---|---|---|---|
| Initial molecular diagnosis (Xpert/Xpert Ultra strategy) | WHO TB diagnosis module and handbook | Implemented (`Xpert`, `DxDelivery`) | Phase 2.1, 2.2, 6.1, 7 | Covered |
| Household contact investigation | WHO preventive treatment and contact prioritization guidance | Implemented (`HouseholdContactTracing`, `TPTHousehold`) | Phase 2.6, 5, 6.2, 8, 11.6 | Covered |
| Preventive treatment for contacts and people at risk | WHO preventive treatment recommendations | Implemented (`TPTSimple`, `TPTDelivery`) | Phase 2.6, 6.2, 7 | Covered |
| Birth BCG in high-burden settings | WHO BCG position paper | Implemented (`BCGVx`, `BCGRoutine`) | Phase 2.5, 6.3, 7 | Covered |
| HIV as major TB risk driver and TB-HIV integration | WHO risk factors and TB/HIV prevention guidance | Implemented (`HIV`, `TB_HIV_Connector`) | Phase 3.1, 6.3, 7 | Covered |
| Undernutrition as major TB determinant | WHO TB determinants reporting | Implemented (`Malnutrition`, `TB_Nutrition_Connector`) | Phase 3.2, 6.3, 7 | Covered |
| Treatment cascade and outcomes (success/failure/relapse) | WHO care cascade principles and standard treatment management | Implemented (`Tx`, `TxDelivery`) | Phase 2.3, 6.1, 7 | Covered |
| Drug-resistant TB pathway and treatment decisions | WHO diagnosis and DR-TB management guidance | Partial (diagnostic support exists; explicit resistance state progression not modeled) | Phase 2 + 6 smoke coverage only | Partial gap |

### B. Evidence-Informed Feature Combination Catalogue

The following combinations are selected because they represent real programmatic TB pathways, not arbitrary cross-products.

| Combination ID | Real-world rationale | Required tbsim features | Test style | Current status |
|---|---|---|---|---|
| C1: Household transmission + contact tracing + TPT | Core WHO prevention pathway for contacts | `HouseholdContactTracing` + `TPTHousehold` + `TPTDelivery` | Integration + invariants + regression | Covered (Phases 2.6, 6.2, 11.6) |
| C2: Symptom onset + health-seeking + rapid molecular diagnosis + treatment | Standard case-finding to treatment cascade | `HealthSeekingBehavior` + `DxDelivery(Xpert)` + `TxDelivery` | End-to-end cascade tests | Covered (Phases 2.2, 2.3, 6.1) |
| C3: HIV + TB connector + diagnosis/treatment | High-priority co-epidemic pathway in many high-burden settings | `HIV` + `TB_HIV_Connector` + care cascade | Differential subgroup comparisons | Covered (Phases 3.1, 6.3, 7) |
| C4: Undernutrition + TB progression + prevention/treatment | High attributable burden from undernutrition in many settings | `Malnutrition` + `TB_Nutrition_Connector` + care cascade | Risk-gradient and burden tests | Covered (Phases 3.2, 6.3, 7) |
| C5: Birth BCG + pediatric progression suppression | WHO neonatal BCG policy alignment | `BCGVx` + `BCGRoutine` + age filters | Age-stratified unit and integration tests | Covered (Phase 2.5 + combinatorial) |
| C6: Migration + household dynamics + cascade eligibility | Realistic demography affects targeting and burden | `Migration` + household + cascade modules | UID/integrity + performance + integration | Covered (Phases 5, 8, 9, 11) |
| C7: Prior TB history + rapid diagnostics behavior | WHO notes nuanced use of Xpert Ultra with recent prior TB | `DxDelivery` + prior-history-aware fixtures | Scenario tests with prior-treatment strata | Not explicit; add below |
| C8: Drug resistance suspicion + diagnostic + regimen branching | Programmatically critical DR-TB flow | diagnostics + treatment branch logic | Branching and pathway validity tests | Partial; add below |

### C. New Test Additions for Not-Yet-Covered or Partially Covered Evidence Areas

The plan already covers many core pathways. The following additions are required to close evidence-alignment gaps.

#### C.1 Add: Prior-TB-History Diagnostic Behavior Tests

**New tests to add (Phase 2 and 6):**

- `test_dx_prior_tb_history_strata`: stratify adults into no prior TB, remote prior TB (>5 years), and recent prior TB (<=5 years), then verify pathway-specific expected behavior and no silent misclassification in result states.
- `test_dx_false_positive_pressure_in_prior_tb_group`: ensure scenario assumptions around specificity trade-offs are explicit and tested, especially for repeated diagnosis workflows.

**Why:** This reflects WHO diagnostic guidance distinctions for prior-treatment history and avoids over-generalized assumptions in validation scenarios.

#### C.2 Add: Drug-Resistance Scenario Branching Tests (Current Partial Gap)

**New tests to add (new subsection in Phase 6 + 7):**

- `test_dr_suspected_branch_routes_to_secondline`: in a DR-suspected fixture, verify treatment branch uses `SecondLine` and never falls back silently to first-line pathways.
- `test_dr_branch_requires_explicit_assumption`: fail if DR pathway is invoked without explicit scenario flags or assumptions.
- `test_dr_pathway_outputs_are_separable`: ensure DR-branch outcomes are reported separately from drug-susceptible outcomes.

**Why:** The model currently has treatment products but no full pathogen resistance state model. Tests must make this limitation explicit and prevent accidental over-claiming.

### D. Evidence Alignment Rules for Ongoing Maintenance

To keep this mapping alive and prevent drift:

1. Any new major feature must include an "Evidence anchor" field in PR description with at least one guideline/paper link.
2. Any feature combination used in publications or decision support must have:
   - one deterministic/invariant test,
   - one stochastic robustness test,
   - one data-integrity test (UID-safe targeting).
3. Any missing evidence-priority feature must be listed in a gap table with owner and target release.

### E. Gap Register (Must Stay Visible at Top of Plan)

| Gap ID | Feature gap | Risk if unaddressed | Planned action |
|---|---|---|---|
| G1 | Prior-TB-history diagnostic stratification not explicit | Overconfident diagnostic assumptions | Add C.1 tests in Phase 2/6 |
| G2 | DR-TB pathway only partially represented | Invalid scenario conclusions for resistance-heavy settings | Add C.2 branch tests; mark limitations explicitly |

### F. Core Evidence References for This Mapping

- WHO TB diagnosis recommendations and module 3 guidance: [WHO consolidated guidelines on TB, Module 3: Diagnosis (3rd ed)](https://www.who.int/publications/i/item/9789240089488)
- WHO TB preventive treatment recommendations: [WHO consolidated guidelines on TB, Module 1: Prevention (2nd ed)](https://www.who.int/publications/i/item/9789240096196)
- WHO household contact prioritization and implementation guidance: [WHO TB Knowledge Sharing: Prioritizing household contacts](https://tbksp.who.int/en/node/2035)
- WHO BCG policy: [BCG vaccines WHO position paper (2018)](https://www.who.int/publications/i/item/who-wer9308-73-96)
- WHO determinant and risk-factor framing: [WHO Global TB Report determinants section](https://www.who.int/teams/global-tuberculosis-programme/tb-reports/global-tuberculosis-report-2024/uhc-and-tb-determinants/5-3-tb-determinants)
- Additional reputable LTBI regimen guidance for contacts: [CDC latent TB treatment guidance](https://www.cdc.gov/tb/hcp/treatment/latent-tuberculosis-infection.html)




---

## Scope and Test Environment

### Package under test

- `tbsim` v0.8.1 and forward
- Dependencies: starsim >= 3.2.1, sciris >= 3.1.0

### Tools and conventions

- Framework: `pytest` with `pytest-cov` for coverage reporting and `pytest-xdist` for parallel execution
- All tests run with `MPLBACKEND=Agg` to suppress display output
- Baseline reference data stored in `tests/data/` as CSV files
- Performance tests use `time.perf_counter`, `tracemalloc`, and baseline ratios with documented hardware assumptions
- Each test file targets a single module or feature area; shared helpers live in `tests/common_functions.py`
- All tests must work both under `pytest` and as standalone scripts, following Starsim testing conventions
- Test files define `n_agents`, `do_plot`, and `sc.options(interactive=False)` at module scope
- Test functions use `@sc.timer()` where practical, include descriptive assertion messages, and return the main object they create
- Plotting is gated behind `if do_plot:` unless the plot object itself is the assertion target

### General conventions

- Population sizes in unit tests are kept small (100-500 agents) to run quickly; integration and performance tests scale up
- CRN-reproducibility checks always run two identical simulations with the same seed and compare result arrays element-by-element
- Any test that depends on stochastic behavior uses a fixed seed and assertions that are loose enough to not break on minor implementation changes (e.g., "prevalence > 0" rather than "prevalence == 0.247")
- Statistical tests use explicit tolerances and explain the tolerance in the assertion message or nearby comment
- Warnings from tbsim and Starsim are treated as failures unless the test explicitly asserts the warning
- `xfail` is allowed only for a documented upstream bug or an accepted not-yet-implemented tbsim issue; every `xfail` must include an issue link and must be reviewed before release
- Any test marked as regression must fail against the bad behavior it is guarding, not merely execute the relevant function
- Coverage does not count as proof. Every new high-risk path needs an oracle: an invariant, a reference calculation, a deterministic fixture, a differential comparison, or a metamorphic relation

---

## Phase 0: Test Architecture and Quality Gates

This phase sets the rules for the test suite itself. Without these gates, a large test count can create false confidence: hundreds of tests can pass while still allowing silent tbsim or Starsim failures through.

### 0.1 Test File Standards

**Test: test_files_follow_starsim_style**

Every test file must be runnable both by `pytest` and as a standalone script. Each file should include:

- Module-level `do_plot = False`
- Module-level `n_agents` where the file creates simulations
- `sc.options(interactive=False)`
- `if __name__ == '__main__':` block that runs the test functions with plotting enabled when useful
- `@sc.timer()` on substantive test functions

This is enforced by a lightweight static test that scans `tests/test_*.py`. The static test should not be overly clever; it exists to catch omissions, not to become a custom linter.

**Test: asserts_have_messages**

All plain `assert` statements in the test suite must include a message that describes the expected behavior. This is important because stochastic and scientific failures are otherwise hard to diagnose from CI logs.

**Test: floats_have_explicit_tolerance**

Float comparisons must use `np.isclose`, `np.allclose`, or a documented relative/absolute tolerance. Direct equality against floats is prohibited unless the value is exactly structural, such as `0.0` after a forced-zero intervention.

**Test: no_silent_expected_failures**

Every `pytest.mark.xfail` must include a reason containing an issue number or URL. A release candidate must run once with strict xfail handling so that newly passing expected failures are noticed.

### 0.2 CI Gates

**Gate: pull_request_fast_suite**

Runs on every PR:

```bash
pytest tests/ -m "not performance and not slow" --cov=tbsim --cov-report=term-missing --strict-markers -W error
```

This suite must finish quickly enough to run on every change. It includes all unit tests, regression tests, and the fast Starsim contract tests.

**Gate: nightly_full_suite**

Runs nightly:

```bash
pytest tests/ -m "not performance" -n auto --strict-markers -W error
```

This includes slow integration, combinatorial, and long-horizon tests.

**Gate: weekly_performance_suite**

Runs weekly and on release candidates:

```bash
pytest tests/performance/ -m performance --tb=short --strict-markers
```

Performance failures block releases but do not block ordinary PRs unless the PR directly changes migration, network, analyzers, TB stepping, or intervention delivery.

**Gate: dependency_matrix**

Run the fast suite against:

- Minimum supported Starsim version from `pyproject.toml`
- Latest released Starsim
- Latest released Sciris

The matrix is mandatory because tbsim depends heavily on Starsim internals such as UIDs, active UIDs, result containers, distributions, module order, and timeline conversion.

### 0.3 Oracle Requirements

Every automated test must use at least one of the following oracles:

| Oracle Type | Example |
|---|---|
| Invariant | State counts sum to the population; cumulative outputs never decrease |
| Deterministic fixture | Forced all-success treatment produces only success outcomes |
| Reference calculation | Product probability rows match hand-computed expected probabilities |
| Differential comparison | High-beta sim produces more TB than low-beta sim under matched seeds |
| Metamorphic relation | Halving coverage roughly halves delivery counts under a fixed eligible cohort |
| Snapshot contract | Starsim UID and active-UID behavior matches the checked-in reference fixture |

Tests that only assert "no exception was raised" are allowed only for plotting backends and smoke tests. They do not count toward release-critical coverage.

## Phase 1: Unit Tests — Core Disease Model

These tests validate the TB natural history model in isolation, independent of interventions, networks, or demographics. The goal is to verify that the state machine transitions are correct, that invariants hold under all inputs, and that rate parameters have the expected directional effects.

### 1.1 Equivalent Classes for TB Agent State

The TB state machine has nine possible states. For unit testing, agents are grouped into the following equivalent classes based on which transitions are available to them:

| Class | States | Transitions Available |
|---|---|---|
| Uninfected | SUSCEPTIBLE, CLEARED | Infection only |
| Latent | INFECTION, NON_INFECTIOUS | Progression, clearance |
| Active | ASYMPTOMATIC, SYMPTOMATIC | Further progression, death |
| Care pathway | TREATMENT | Cure, failure, relapse |
| Terminal | DEAD, REMOVED | None |

Each class must be represented in unit tests for the `transition()` method.

### 1.2 State Machine Invariants

**Test: state_sum_equals_population**

At every timestep, the sum of agents across all mutually exclusive TB states must equal the total agent count represented in the sim, including terminal states such as DEAD and REMOVED. Separately, the sum across non-terminal states must equal the alive population. Both assertions are needed because a test that only checks live agents can miss leakage into terminal states.

**Test: cumulative_results_non_decreasing**

Results labeled `cum_*` (e.g., `cum_active`, `cum_deaths`) must never decrease across timesteps.

**Test: prevalence_bounded**

`prevalence_active` must remain in `[0, 1]`. This must hold even when beta is set to extreme values.

**Test: incidence_non_negative**

`incidence_kpy` must not go negative at any timestep. Edge case: a population that starts with zero infections.

**Test: n_infectious_consistent**

`n_infectious` must equal the count of agents in `ASYMPTOMATIC` or `SYMPTOMATIC` states at every step.

### 1.3 Transition Rate Sensitivity

**Test: higher_beta_higher_prevalence**

Run two simulations that are identical except for beta. The high-beta run must produce higher average prevalence over the run period. Uses a paired comparison with a fixed seed.

**Test: higher_activation_rate_fewer_latent**

Increasing `inf_non` or `inf_asy` (the latency-to-active progression rates) should reduce the duration agents spend in latent states, increasing active TB faster.

**Test: higher_clearance_rate_lower_prevalence**

Increasing `non_rec` or `asy_non` (recovery rates) should reduce active TB burden.

**Test: rr_death_multiplicative**

Manually set `rr_death` to 2.0 for a cohort and verify that the observed mortality rate is approximately double the baseline.

**Test: waning_reinfection_protection**

Set `dur_reinfection_protection` to a known value, infect a cohort that has previously cleared infection, wait past the protection window, and confirm reinfection occurs.

### 1.4 Initialization

**Test: init_prev_respected**

After initialization, the proportion of infected agents must be close to `init_prev` (within 3 standard deviations for the population size used).

**Test: init_state_distribution**

When `init_prev` is nonzero, verify that all latent and active substates receive at least some agents at t=0 (no state is initialized as permanently empty).

**Test: zero_init_prev**

A simulation with `init_prev=0` and no imported infections must produce zero cases throughout.

### 1.5 Death Handling

**Test: dead_agents_not_in_transitions**

Agents in DEAD state must not transition to any other state, must not contribute to force of infection, and must not appear in care-seeking eligibility.

**Test: step_die_removes_from_active_states**

`step_die()` must move dying agents out of SYMPTOMATIC/ASYMPTOMATIC into DEAD and correctly update both state arrays and result counts.

### 1.6 dt Sensitivity

**Test: coarse_vs_fine_dt_agreement**

Run 10 simulation years with `dt=7 days` versus `dt=1 day` and verify that cumulative results agree within 5% at the end of the run. This catches unit conversion errors in rate parameters.

---

## Phase 2: Unit Tests — Interventions

Each intervention is tested in isolation, using a minimal simulation with no other interventions active.

### 2.1 Diagnostic Products

**Equivalent classes for diagnostic testing:**

| Class | Description |
|---|---|
| Active smear-positive | SYMPTOMATIC agents |
| Active smear-negative | ASYMPTOMATIC agents |
| Non-active infectious | NON_INFECTIOUS agents |
| Latent | INFECTION, CLEARED agents |
| HIV-co-infected | FujiLAM-relevant subgroup |
| Children (< 15 years) | Age-stratified products |
| Adults (>= 15 years) | Age-stratified products |

**Test: xpert_sensitivity_by_state**

Run `Xpert.administer()` on a population with known state distribution. The positive rate among SYMPTOMATIC adults must be close to 0.909; among ASYMPTOMATIC adults close to 0.775. Statistical tolerance: ± 3 SE for 1000-agent trials.

**Test: oral_swab_sensitivity_by_state**

Same as above for `OralSwab` — 80%/30%/25% by state and age.

**Test: fujilam_hiv_stratification**

Confirm that HIV-positive agents yield ~75% positivity and HIV-negative agents yield ~58%.

**Test: cad_uniform_sensitivity**

`CAD` applies the same 66% sensitivity to all active states. Confirm there is no age or HIV stratification.

**Test: probability_rows_sum_to_one**

For all built-in `Dx` products, the output probability matrix must have rows that sum to 1.0 within floating-point tolerance after `build()`. The test must also assert that no probability is negative and no probability is greater than 1.0.

**Test: dx_product_with_empty_uid_array**

Calling `administer()` with zero UIDs must return an empty result dict without raising exceptions.

### 2.2 DxDelivery

**Test: only_symptomatic_eligible_by_default**

Without `HealthSeekingBehavior`, no agents receive diagnosis by default because `sought_care` is never set. With HSB active, at least some symptomatic agents should be flagged positive over a 5-year run.

**Test: coverage_scales_tested_count**

Run two identical DxDelivery setups with coverage 0.25 and 1.0. The high-coverage run must produce approximately 4x the number of tests. Margin: ±30% due to stochasticity.

**Test: result_expiry_re_eligibility**

Set `result_validity` to 30 days. After 31 days, an agent whose result has expired must be eligible for re-testing.

**Test: custom_result_state_set**

Pass a custom `result_state` to DxDelivery. Confirm that positives are marked with that state, not the default `diagnosed` flag.

**Test: uid_position_safety_after_deaths**

Regression for #425. After agents have died in mid-simulation, confirm that DxDelivery does not apply results to agents at wrong positions. Verify using a sim where many early deaths are forced and check that no dead agent appears in results.

### 2.3 Treatment Products and TxDelivery

**Equivalent classes for treatment testing:**

| Class | Description |
|---|---|
| Active-only | Only SYMPTOMATIC/ASYMPTOMATIC agents present |
| Latent-only | Only INFECTION/NON_INFECTIOUS present |
| Mixed | Both active and latent agents |
| Empty | Zero eligible agents |

**Test: tx_efficacy_one_all_cure**

Set `efficacy=1.0` and `p_relapse=0`. All treated agents must end up in the success bucket. No failures or relapses.

**Test: tx_efficacy_zero_all_fail**

Set `efficacy=0.0`. All treated agents must fail or relapse (no cures).

**Test: adherence_zero_no_treatment**

Set `adherence=0.0`. No agents should receive the drug effect — all must fail.

**Test: step_start_treatment_latent_only**

Feed only INFECTION-state UIDs to `_step_start_treatment()`. Confirm that latent agents are handled correctly (cleared immediately on treatment start per the LSHTM model).

**Test: step_start_treatment_mixed**

Mix latent and active UIDs. Verify that each group is routed to the correct treatment pathway.

**Test: relapse_scheduled_correctly**

After a simulated successful treatment, a relapse-flagged agent must return to SYMPTOMATIC after `dur_relapse` timesteps. Verify using a controlled cohort with forced outcomes.

**Test: tx_delivery_uid_position_safety**

Same as DxDelivery regression for #425 — confirm dead agents are not inadvertently treated.

**Test: all_builtin_products_run**

`DOTS`, `DOTSImproved`, `FirstLine`, `SecondLine`, and any `TxMulti` product must instantiate, administer to a deterministic eligible cohort, and produce a complete partition of outcomes: every treated UID appears in exactly one of success, failure, or relapse. A full-sim smoke run is useful but not sufficient.

**Test: tx_crn_reproducibility**

Run the same sim twice with the same seed. Result arrays for `n_treated`, `n_success`, `n_failure` must be element-wise identical.

### 2.4 Health Seeking Behavior

**Test: no_seeking_without_symptomatic_agents**

A sim with zero active TB must produce zero `new_sought_care` at every step.

**Test: seeking_only_for_symptomatic**

In a mixed-state population, only SYMPTOMATIC agents must have `sought_care` set. ASYMPTOMATIC and latent agents must never be flagged.

**Test: one_shot_per_episode**

An agent who has sought care must not seek care again in the same symptomatic episode unless `care_retry_steps` is set and the retry interval has elapsed.

**Test: care_retry_fires_at_interval**

Set `care_retry_steps=14`. Confirm that an agent who sought care at step 0 can seek again at step 14, but not at step 13.

**Test: date_window_restricts_seeking**

Set HSB active only between years 2005 and 2010. Confirm zero seeking before 2005 and after 2010, and nonzero seeking during the window.

**Test: hsb_uid_position_safety**

Regression for #425. Force deaths early in the run and confirm that `sought_care` is never applied to agents at stale positions.

**Test: missing_tb_raises_keyerror**

A sim with no TB disease module attached must raise `KeyError` or an equivalent informative exception when HSB runs.

### 2.5 BCG

**Test: bcg_age_range_filter**

BCG with `age_min=0, age_max=5` must never vaccinate an agent older than 5. Verify by checking ages of all agents with active BCG protection.

**Test: bcg_coverage_filter**

BCG with `coverage=0.5` must vaccinate approximately 50% of eligible agents in the delivery window. Check over multiple seeds.

**Test: bcg_rr_modifiers_written**

After BCG protection is applied, the vaccinated agent's TB `rr_activation` must be < 1.0 and `rr_clearance` must be > 1.0. Verify at the step immediately after delivery.

**Test: bcg_protection_expiry**

Set `dur_immune` to a short value (e.g., 30 days). After 30 days, the agent's RR modifiers must return to 1.0.

**Test: bcg_offered_only_once**

A BCGRoutine that is set to one-time delivery must not vaccinate the same agent twice, even if the agent remains in the eligible age range across multiple steps.

**Test: bcg_result_counts**

After a run with BCG active, `n_newly_initiated` must be > 0 and `n_protected` must be <= `n_newly_initiated`.

### 2.6 TPT

**Test: tpt_simple_targets_infection_state**

`TPTSimple` must only deliver to agents in INFECTION state. Verify that SUSCEPTIBLE and active-TB agents are excluded.

**Test: tpt_two_phase_sequence**

After administration, confirmed-effective agents must first receive the efficacy draw, then the sterilization-vs-suppression draw. Agents in the sterilize bucket must have INFECTION cleared; agents in the suppress bucket must have `rr_*` modifiers applied.

**Test: tpt_suppression_modifier_applied**

For a suppressed agent, verify `rr_activation < 1.0` during `dur_protection` and that the modifier returns to baseline after the protection expires.

**Test: tpt_no_delivery_to_tx_agents**

Agents currently on TB treatment must be excluded from TPT delivery (they are in TREATMENT state, not INFECTION).

**Test: tpt_household_tracing_finds_contacts**

In a household network with known structure, `TPTHousehold` must correctly identify household members of newly-treated index cases and mark them with `contact_identified`.

**Test: tpt_household_no_retrigger**

The same index case should not trigger a new household contact tracing event in consecutive steps unless a new treatment start occurs.

**Test: hct_uid_position_safety**

Regression for #425. After mid-run deaths, confirm `HouseholdContactTracing` does not assign `contact_identified` to agents at wrong positions.

**Test: tpt_sterilize_vs_suppress_mutual_exclusive**

A single agent cannot be in both the sterilization and suppression buckets after a single TPT administration.

### 2.7 BetaByYear

**Test: single_year_change_applied_once**

A `BetaByYear` with a single year entry must modify beta exactly once and must not re-apply the change in subsequent steps.

**Test: multi_year_changes_compound**

Two successive BetaByYear entries at years Y1 and Y2 must apply multiplicatively. Verify by comparing final beta to expected compounded value.

**Test: beta_change_affects_incidence**

A simulation where beta is halved at year 5 must show lower incidence in years 5-10 compared to a baseline with constant beta.

---

## Phase 3: Unit Tests — Comorbidities

### 3.1 HIV

**Equivalent classes for HIV state:**

| Class | HIV State | Expected TB Effect |
|---|---|---|
| Uninfected | None | No modifier |
| Acute phase | ACUTE | 1.22x activation |
| Latent/chronic | LATENT | 1.90x activation |
| AIDS | AIDS | 2.60x activation |
| On ART | LATENT or AIDS + ART | Reduced progression |

**Test: hiv_state_initialization**

After `init_prev=0.1` and `init_onart=0.5`, approximately 10% of agents should be HIV-positive and approximately 50% of those should be on ART. Verify with tolerance of ± 3 SE.

**Test: tb_hiv_connector_rr_values**

For agents in each HIV state, the `TB_HIV_Connector` must write the correct `rr_activation` multiplier to the TB module. Verify at a single timestep using a population with forced HIV states.

**Test: art_reduces_progression**

Agents on ART must transition from ACUTE to LATENT and from LATENT to AIDS more slowly than those not on ART. Run two cohorts for 20 years and compare cumulative state transitions.

**Test: hiv_interventions_target_coverage**

`HivInterventions` must move prevalence toward the specified target within 5 years. Verify that simulated HIV prevalence is within 20% of the target by the end of the run.

**Test: no_hiv_no_modifier**

A sim that includes `TB_HIV_Connector` without the required HIV or TB module must fail loudly during initialization with an informative exception. A missing dependency must not silently leave `rr_activation` unchanged, because that would hide misconfigured simulations.

### 3.2 Malnutrition

**Equivalent classes for nutritional state:**

| Class | Condition |
|---|---|
| Well-nourished | Weight/height > 50th percentile |
| Mildly malnourished | 20th-50th percentile |
| Severely malnourished | < 20th percentile (micro < 0.2) |
| Receiving supplementation | macro + micro intervention |

**Test: lms_data_loads**

`anthropometry.csv` must load without error and produce valid LMS coefficients for all age groups.

**Test: weight_percentile_bounded**

Over any 10-year run, `weight_percentile` must remain in `[0, 1]` for all agents.

**Test: relsus_elevated_below_threshold**

Agents with `micro < 0.2` must receive `rel_sus = 2.0` from the default `TB_Nutrition_Connector`. Agents above threshold must receive `rel_sus = 1.0`.

**Test: supplementation_rr_halved**

The `supplementation_rr` static method must return 0.5 for agents receiving both macro and micro supplementation.

**Test: lonnroth_bmi_rr_sigmoid_shape**

`lonnroth_bmi_rr` must produce values > 1.0 for low BMI and values approaching 1.0 for high BMI. Verify at BMI = 16, 18.5, 25, 30.

**Test: malnutrition_raises_tb_burden**

A sim with `Malnutrition` and `TB_Nutrition_Connector` active must produce higher active TB prevalence than an equivalent sim without malnutrition, given the same initial conditions.

---

## Phase 4: Unit Tests — Analyzers and Plots

### 4.1 DwellTime Analyzer

**Test: dwell_time_attaches_to_sim**

`DwellTime()` added to a sim's analyzers list must produce a non-empty DataFrame after the sim completes. The DataFrame must include UID, previous state, next state, start step, and end step columns, and all UIDs must belong to agents that existed during the recorded interval.

**Test: dwell_time_records_all_state_transitions**

For a population where state transitions are forced deterministically, verify that every transition appears in the DwellTime output with the correct agent UID and step.

**Test: dwell_time_save_and_load**

Call `save(filename)` after a run. The resulting CSV must load back into a `DwellTime(file_path=...)` instance without data loss.

**Test: dwell_time_aggregate_mode**

Write two DwellTime CSVs to a temporary directory. Load them with `DwellTime(directory=...)` and confirm the concatenated output has the correct number of rows.

**Test: dwell_time_plot_modes**

Call `plot(kind='histogram')` and `plot(kind='kaplan_meier')` in succession. Each call must create a figure with at least one axis and at least one plotted artist. Agg backend is used, so the test inspects matplotlib objects rather than displaying the plot.

### 4.2 HouseholdStats Analyzer

**Test: household_stats_result_dimensions**

After a 10-year run with `HouseholdStats` attached, `mean_hh_size` must be a time series with one value per timestep.

**Test: mixing_matrix_shape**

The age-mixing matrices saved at `t=0` and `t=final` must be square with dimension equal to the number of age bins.

**Test: from_multisim_averages**

Run 3 replicates with `HouseholdStats`. `HouseholdStats.from_multisim(msim)` must return a single object whose `mean_hh_size` is element-wise between the min and max of the individual replicates.

**Test: mean_hh_size_plausible**

For a sim initialized with household sizes drawn from a Poisson(3) distribution, `mean_hh_size` at t=0 must be between 2.0 and 5.0.

### 4.3 Plots

**Test: plot_accepts_sim**

`tbsim.plot(sim)` with a completed sim must return or create at least one figure with non-empty axes and plotted result data. The test should inspect the matplotlib object rather than only checking for absence of exceptions.

**Test: plot_accepts_multisim**

`tbsim.plot(msim)` with a completed MultiSim must overlay one series per scenario or replicate for the selected metric. The assertion should inspect the number of plotted lines or collections.

**Test: plot_select_like**

`plot(sim, select=dict(like='prevalence'))` must only include series whose names contain "prevalence".

**Test: plot_select_exclude**

`plot(sim, select=dict(exclude=['n_dead']))` must not include `n_dead` in the output.

**Test: plot_household_layouts**

`plot_household()` must run for all four layout modes: `ring`, `grid`, `spring`, `kamada`. For a known three-household fixture, the graph must contain exactly the expected number of nodes and household/contact edges.

---

## Phase 5: Unit Tests — Migration

### 5.1 Equivalent Classes for Migration

| Class | Condition |
|---|---|
| Net immigration | immigration_rate > emigration_rate |
| Net emigration | emigration_rate > immigration_rate |
| Balanced | immigration_rate == emigration_rate |
| High TB-prevalence immigrants | tb_state_distribution weighted to active TB |
| Zero migration | Both rates = 0 |

**Test: net_immigration_grows_population**

After 5 years with only immigration active, population must be larger than the initial size.

**Test: net_emigration_shrinks_population**

After 5 years with only emigration active, population must be smaller than the initial size.

**Test: balanced_migration_stable_population**

With `maintain_population=True`, population must remain within 10% of initial size throughout the run.

**Test: high_prevalence_immigration_raises_burden**

A sim that imports agents with high TB burden must show higher prevalence than a no-migration baseline after 5 years, all else equal.

**Test: emigration_removes_agents**

After emigration events, the emigrated agents must not appear in any state counts, must not receive interventions, and must not transmit disease.

**Test: migration_results_tracked**

`n_immigrants`, `n_emigrants`, and `net_migration` must all be populated after a run. Net migration must equal `n_immigrants - n_emigrants` at every step.

**Test: household_uid_safety_after_migration**

Regression for #425. After emigrants are removed, the remaining agents must maintain correct UID-to-position mapping. Verify by checking that household membership lists contain only alive UIDs.

**Test: age_distribution_respected**

The age distribution of immigrants sampled over 1000 events must match the specified `immigration_age_distribution` within 10% per bin.

**Test: zero_migration_no_change**

A sim with both rates at zero must produce identical results to the same sim with no Migration module.

---

## Phase 6: Integration Tests — Cascade Chains

Integration tests verify that multiple modules work correctly when connected. Each test runs a full simulation with a defined cascade configuration and checks end-to-end results.

### 6.1 Standard Care Cascade

**Test: full_cascade_hsb_dx_tx**

Run a 10-year sim with `HealthSeekingBehavior → DxDelivery(Xpert) → TxDelivery(DOTS)`. Verify:
- `n_tested > 0` (HSB feeds DxDelivery)
- `n_positive > 0` (DxDelivery finds cases)
- `n_treated > 0` (TxDelivery receives diagnosed agents)
- `cum_deaths` is lower than a no-intervention baseline

**Test: cascade_coverage_ordering**

At 80% coverage at each of three cascade steps, the final treatment rate must be approximately `0.8^3 = 51.2%` of the eligible symptomatic population. Margin: ±20%.

**Test: cascade_without_hsb**

Without `HealthSeekingBehavior`, a DxDelivery with the default eligibility filter must produce zero tests (since `sought_care` is never set).

**Test: cascaded_dx_second_product**

Two DxDelivery modules in sequence — the second with a custom `result_state` — must correctly chain: agents failing the first test become eligible for the second.

### 6.2 TPT Cascade

**Test: tpt_household_cascade**

Run a sim with `TxDelivery → HouseholdContactTracing → TPTDelivery`. After treatment starts for index cases, household contacts must be identified and receive TPT. Verify `n_contacts_identified > 0` and `n_newly_initiated > 0` in TPTDelivery results.

**Test: tpt_prevents_progression**

In a sim with TPT and without TPT, the with-TPT sim must show fewer INFECTION-to-active transitions over the run period.

### 6.3 Comorbidity Integration

**Test: tbhiv_connector_active**

Run a sim with `TB + HIV + TB_HIV_Connector`. The HIV-positive subgroup must show higher active TB incidence than the HIV-negative subgroup over a 10-year period.

**Test: tb_malnutrition_connector_active**

Run a sim with `TB + Malnutrition + TB_Nutrition_Connector`. The severely malnourished subgroup (`micro < 0.2`) must have higher TB susceptibility (`rel_sus`) than the well-nourished subgroup.

**Test: tbhiv_plus_bcg**

Adding BCG to a TB+HIV sim must not raise exceptions and must produce lower active TB prevalence in the vaccinated cohort.

### 6.4 Compartmental vs Agent-Based Agreement

**Test: ode_vs_ss_agreement**

Run `TB_ODE` and `TB_SS` over the same 50-year period with identical parameters. The final values for total infectious fraction and total cumulative deaths must agree within 5%.

**Test: tb_ode_runs_to_completion**

`TB_ODE.run()` over a 100-year period must complete without raising exceptions and must return finite values (no NaN or Inf) in all compartments.

**Test: tb_ss_runs_to_completion**

`TB_SS` embedded in an `ss.Sim` must run 100 years and produce finite, non-negative values for every compartment at the final timestep.

---

## Phase 7: Combinatorial Tests

Combinatorial tests use structured input combinations to maximize defect detection while keeping the number of tests manageable. Two techniques are applied: equivalence class combinations and pairwise (all-pairs) intervention combinations.

### 7.1 Pairwise Intervention Matrix

The interventions form the following factor table. All-pairs coverage is generated by a checked-in script; the generated table is committed as `tests/data/pairwise_intervention_cases.csv`. The plan must not claim a fixed number of cases unless the generator verifies it, because the minimum row count can change when factors are added or constrained.

| Factor | Values |
|---|---|
| BCG | On / Off |
| TPT (type) | TPTSimple / TPTHousehold / Off |
| Diagnostic | Xpert / OralSwab / FujiLAM / CAD / Off |
| Treatment | DOTS / FirstLine / SecondLine / Off |
| HIV comorbidity | On / Off |
| Malnutrition comorbidity | On / Off |
| Migration | On / Off |

**Seed cases expected in the pairwise table:**

- `test_combo_bcg_tptsimple`: BCG + TPTSimple + Xpert + DOTS, no comorbidities
- `test_combo_bcg_tpthousehold`: BCG + TPTHousehold + Xpert + FirstLine
- `test_combo_hiv_cad_dots`: HIV + CAD + DOTS, no BCG or TPT
- `test_combo_malnutrition_oralswab`: Malnutrition + OralSwab + DOTS
- `test_combo_hiv_malnutrition_full`: Both comorbidities + BCG + Xpert + FirstLine
- `test_combo_migration_active`: Migration + BCG + Xpert + DOTS, no comorbidities
- `test_combo_fujilam_hiv`: HIV + FujiLAM + SecondLine
- `test_combo_no_interventions`: Only TB disease model, no interventions
- `test_combo_all_interventions`: Every module active simultaneously

Each combo test asserts: (a) result arrays are finite, (b) cumulative results are non-decreasing, (c) module-specific sentinel outputs are present when that module is enabled, and (d) disabled modules do not leave behind nonzero outputs. "No unhandled exceptions" is not enough to pass a combinatorial test.

### 7.2 Coverage Level Equivalence Classes

Coverage is partitioned into three equivalence classes. Each class must be tested for every delivery intervention:

| Class | Value | Expected Behavior |
|---|---|---|
| Zero | 0.0 | No deliveries; all counts remain 0 |
| Partial | 0.5 | Approximately half the eligible population reached |
| Full | 1.0 | All eligible agents reached each step |

**Test template: coverage_class_{intervention}_{class}**

Example: `test_coverage_class_dx_zero`, `test_coverage_class_tx_partial`, `test_coverage_class_bcg_full`

Total coverage-class tests: 4 interventions × 3 classes = 12 tests

### 7.3 Population Size Equivalence Classes

Population size affects stochastic variance, boundary conditions, and performance. Four classes:

| Class | n_agents | Purpose |
|---|---|---|
| Minimal | 50 | Edge case: empty states early in run |
| Small | 500 | Standard unit test size |
| Medium | 5000 | Standard integration test size |
| Large | 50000 | Performance boundary (see Phase 9) |

All Phase 1 invariant tests (state sum, prevalence bounded, cumulative non-decreasing) must pass for all four population sizes.

### 7.4 Temporal Combination Tests

**Test: interventions_start_mid_run**

Start all interventions at year 5 of a 10-year run (i.e., no interventions for the first 5 years). Confirm that pre-intervention years show no intervention effect and post-intervention years do.

**Test: interventions_stop_mid_run**

Active interventions that are set to end at year 5 must produce results only in the first 5 years.

**Test: beta_by_year_with_concurrent_interventions**

`BetaByYear` halving beta at year 5, combined with `HealthSeekingBehavior + DxDelivery + TxDelivery`, must produce a measurable additional reduction in incidence compared to either alone.

### 7.5 Seed and CRN Reproducibility

**Test: identical_seeds_identical_results**

Two runs with the same seed must produce bit-for-bit identical result arrays for: `prevalence_active`, `n_treated`, `n_success`, `n_failure`, `n_immigrants`.

**Test: different_seeds_different_results**

Two runs with different seeds must differ in at least one result time series. (This confirms that randomness is actually being used.)

**Test: multisim_seed_isolation**

In a MultiSim with 4 replicates, each replicate must produce different results from the others, and re-running the same MultiSim must reproduce the same 4 result sets.

---

## Phase 8: Regression Tests

These tests specifically guard against bugs that have been found and fixed in the commit history. Each regression test is tied to a specific issue number.

### 8.1 Issue #425 — UID/Position Confusion

This bug caused several modules to use `.values` (compact alive-index positions) where `.auids` (stable UIDs) were needed, leading to incorrect agent targeting after deaths.

**Regression test structure:** All #425 regression tests use the same setup — a small simulation with a high death rate (`death_rate = 200`) that forces many agent deaths in the first 20 steps. After the deaths, each affected module is verified to not apply its action to agents at stale positions.

- `test_regression_425_hct_step` — `HouseholdContactTracing.step()`
- `test_regression_425_tpthousehold_eligibility` — `TPTHousehold.check_eligibility()`
- `test_regression_425_txdelivery_get_eligible` — `TxDelivery._get_eligible()`
- `test_regression_425_migration_members_by_hhid` — `Migration._members_by_household_id()`
- `test_regression_425_hsb_step` — `HealthSeekingBehavior.step()`

Each test must assert that no dead agent appears in the output UID list of the affected method.

### 8.2 Household Emigrant Removal

From the migration development history (bug fixes: b85ffc5, 7336e5d, afb5af7), three specific edge cases were identified:

**Test: hhid_bincount_contiguous_ids**

When household IDs are non-contiguous (e.g., after emigrant removal), `_members_by_household_id` must still return correct membership without treating the ID gap as a household.

**Test: emigration_age_last_bin_boundary**

Agents at exactly the upper boundary age of the last bin in `emigration_age_distribution` must be handled without index-out-of-bounds errors.

**Test: early_return_on_empty_age_bins**

If the `immigration_age_distribution` dict has bins that don't cover the full age range, `init_pre` must raise a meaningful error rather than silently producing garbage ages.

### 8.3 Performance Optimization Regressions

From commit f838272, three vectorization optimizations were applied to the migration module:

**Test: migration_vectorized_hh_grouping**

The per-household grouping step must complete in < 200ms for 10,000 immigrants being assigned in a single timestep. (Guards against regression to the old one-at-a-time loop.)

**Test: migration_searchsorted_weights**

Verify that `_emig_weights_for_uids` produces the same output when using `np.searchsorted` as a naive loop reference implementation. Test with 5000 agents.

**Test: migration_isin_fallback**

When the exponential-key emigrant sampler falls back to `np.isin`, the result must be the same as the primary path for a fixed seed.

### 8.4 Deleted Module Guard

**Test: tbacute_removed**

Importing `tbsim` and checking for `TBAcute` must raise `AttributeError`. This confirms that the deprecated module removed in v0.8.0 has not been re-introduced.

**Test: immigration_class_removed**

Same for `Immigration` class — must not be present in the `tbsim` namespace.

---

## Phase 9: Performance Tests

Performance tests are run separately from the main test suite using the `pytest -m performance` marker. They establish baselines and enforce upper bounds on runtime and memory. Thresholds are expressed as ratios against checked-in baselines and include the CI machine type, CPU count, Python version, Starsim version, and operating system in `tests/performance_baselines.json`. Absolute ceilings are kept only as emergency guards.

### 9.1 Simulation Throughput

**Test: perf_small_sim_runtime**

A 10-year sim with 1,000 agents, no interventions, must complete within 2x the checked-in baseline on the same CI class. An emergency absolute ceiling of 10 seconds is used only to catch severe hangs.

**Test: perf_medium_sim_runtime**

A 10-year sim with 10,000 agents and a full cascade (HSB + Xpert + DOTS) must complete within 2x the checked-in baseline on the same CI class. An emergency absolute ceiling of 60 seconds is used only to catch severe regressions.

**Test: perf_large_sim_runtime**

A 10-year sim with 50,000 agents, no interventions, must complete within 2x the checked-in baseline on the same CI class. This is the scale at which UID/position operations become expensive enough to catch vectorization regressions. The emergency absolute ceiling is 300 seconds.

**Test: perf_compartmental_ode_runtime**

`TB_ODE.run()` over a 100-year period must complete within 2x the checked-in baseline on the same CI class. An emergency absolute ceiling of 5 seconds is used only to catch severe hangs.

### 9.2 Migration Scalability

**Test: perf_migration_high_turnover**

A sim with 10,000 agents and `immigration_rate = emigration_rate = 0.10` (i.e., 10% population turnover per year) must complete 10 years within 2x the checked-in baseline on the same CI class. This stresses the household assignment and edge cleanup logic. An emergency absolute ceiling of 120 seconds is used only to catch severe regressions.

**Test: perf_migration_batch_immigrant_assignment**

Assigning 1,000 immigrants to existing households in a single step must complete within 2x the checked-in microbenchmark baseline. Regression guard for commit 2e7107d.

### 9.3 Memory

**Test: perf_memory_10k_agents**

A 10-year sim with 10,000 agents must not use more than 2 GB of peak memory. Measured with `tracemalloc`.

**Test: perf_memory_growth_rate**

Peak memory usage must scale sub-linearly with agent count between 1000 and 50,000 agents. The 50x agent increase must not produce more than a 30x memory increase.

### 9.4 Analyzer Overhead

**Test: perf_dwelltime_overhead**

A sim with `DwellTime` attached must run no more than 2x slower than the same sim without it, for 5000 agents over 5 years.

**Test: perf_householdstats_overhead**

Same comparison for `HouseholdStats`. Maximum overhead: 1.5x.

### 9.5 Parallel Execution

**Test: perf_multisim_parallel_speedup**

Running 4 replicates in parallel (via starsim's parallel support or `pytest-xdist`) must complete faster than running 4 replicates sequentially. Minimum expected speedup: 2x on a 4-core machine.

---

## Phase 10: System Tests — `tbsim.Sim` Wrapper

These tests treat `tbsim.Sim` as a black box and validate the user-facing API.

**Test: sim_default_construction**

`tbsim.Sim()` must instantiate and expose the documented defaults: 5,000 agents, start=2000, stop=2010, dt=7 days, one TB disease, one RandomNet, Births, and Deaths. The test must inspect the constructed object rather than relying on construction alone.

**Test: sim_flat_par_routing_tb**

`tbsim.Sim(beta=ss.peryear(0.4))` must route `beta` to the TB module, not the sim-level parameters.

**Test: sim_tb_pars_override**

`tbsim.Sim(tb_pars=dict(init_prev=ss.bernoulli(0.05)))` must produce initial prevalence of approximately 5%.

**Test: sim_prebuilt_tb_model**

Constructing with `tbsim.Sim(tb_model=tbsim.TB(pars=dict(beta=ss.peryear(0.5))))` must use the provided instance and not create a second TB module.

**Test: sim_get_tb**

`sim.get_tb()` must return the TB module. `sim.get_tb('tb')` must return the same result when the module is named `'tb'`.

**Test: sim_get_dx**

A sim with `DxDelivery(name='xpert_dx', ...)` attached must return that instance via `sim.get_dx('xpert_dx', result_state)`.

**Test: sim_get_hsb**

`sim.get_hsb()` must return the `HealthSeekingBehavior` instance.

**Test: sim_plot_runs**

`sim.plot()` and `sim.plot('tb')` must produce figures with non-empty axes and plotted data on a completed sim.

**Test: demo_runs**

`tbsim.demo(run=True, plot=False)` must return a completed sim with finite TB result arrays and at least one TB disease module attached.

---

## Phase 11: Starsim Contract and Canary Tests

This phase exists because tbsim is built on Starsim internals. If Starsim changes how UIDs, active UIDs, result arrays, module ordering, distributions, or date conversion work, tbsim can produce plausible-looking but wrong outputs. These tests are intentionally narrow and explicit. Their job is to fail loudly when an upstream behavior changes.

### 11.1 UID and Indexing Contract

**Test: starsim_uid_active_uid_contract**

Create a small Starsim population with known UIDs. Kill or remove selected agents. Assert the following:

- `people.auids` contains stable UIDs for active agents
- Boolean masks over Starsim arrays select active positions, not stable UIDs
- `arr.auids[mask]` returns the expected stable UIDs
- `arr.values[mask]` is never used as a UID source in tbsim code paths

This test should include a checked-in fixture showing the expected UID/position table before and after deaths.

**Test: no_values_mask_as_uid_pattern**

Static regression test. Scan `tbsim/**/*.py` for dangerous patterns such as `.values[mask]`, `.values[inds]`, or `.values[...]` being passed into methods that expect UIDs. This will not catch every bug, but it catches the exact shape of issue #425 before runtime.

This static test is extended to catch the exact footgun documented in Starsim issue #1356:

- `np.asarray(arr)` on UID-aware arrays used in UID-sensitive paths
- `np.flatnonzero(mask)` feeding `ss.uids(...)`
- `np.where(np.asarray(arr) ...)[0]` feeding `ss.uids(...)`
- any construction pattern equivalent to compact-alive positional indices reinterpreted as stable UIDs

**Test: uid_round_trip_after_births_deaths_migration**

Run a sim with births, deaths, and migration for 2 years. For every alive UID, verify that indexing through Starsim's UID helpers returns the same agent attributes as direct active-agent views. This test protects against subtle Starsim behavior changes after population resizing.

**Test: fail_on_compact_position_reinterpretation**

Construct a fixture with known UID gaps after deaths (example: alive UIDs `[0, 1, 2, 4, 5, 8]`). Intentionally derive compact positions from `np.asarray(arr)` and `np.flatnonzero`, then attempt to reinterpret them as UIDs using `ss.uids(...)`. The test must fail loudly by invariant checks:

- household or contact relationships derived from the reinterpreted UIDs do not match the expected source relationships
- the mismatch is detected by an explicit assertion with a descriptive message

This is a negative canary test: if it starts passing without explicit Starsim warnings or validation behavior, review is required because semantics may have changed.

### 11.2 Module Execution Order Contract

**Test: module_order_rr_modifiers_before_tb_reset**

Create two tiny custom Starsim modules for testing only: one writes a known TB `rr_activation` value and one records the value before and after TB `step()`. Assert that intervention and connector modifiers are applied in the expected order relative to TB progression and reset. If Starsim changes module ordering, this test should fail before any epidemiological tests are interpreted.

**Test: intervention_step_order_cascade_flags**

In a one-step fixture, assert the order of `HealthSeekingBehavior`, `DxDelivery`, and `TxDelivery` flag changes. Specifically:

- HSB sets `sought_care`
- DxDelivery reads `sought_care` and sets the diagnostic result flag
- TxDelivery reads the diagnostic result flag and starts treatment
- Reset logic does not clear a flag before downstream modules read it

This catches silent cascade failures caused by upstream changes to intervention ordering.

### 11.3 Time and Rate Conversion Contract

**Test: starsim_time_conversion_contract**

For `dt=1 day`, `dt=7 days`, and `dt=30 days`, assert that Starsim date conversion and tbsim rate conversion agree for `ss.perday`, `ss.peryear`, `ss.freqperyear`, and `ss.dur`. The expected values should be computed directly in the test from calendar days, not copied from Starsim outputs.

**Test: timeline_boundary_contract**

Interventions scheduled at exact year boundaries must fire on the intended timestep for all supported date formats (`int`, `str`, `ss.date`). This protects `BetaByYear`, routine BCG, and date-windowed health seeking.

### 11.4 Distribution and Randomness Contract

**Test: starsim_distribution_seed_contract**

For the distributions used by tbsim (`bernoulli`, `poisson`, `choice`, `uniform`, `exponential`, and rate wrappers), two distributions initialized with the same seed and same UIDs must produce identical draws. Different UIDs with the same seed must not all receive identical draws.

**Test: uid_order_invariance_for_products**

For products that are expected to be UID-order safe, administer to the same UID set in sorted order and shuffled order. The output set membership should be identical when CRN behavior is supported. For known non-CRN-safe paths, the test is marked `xfail` with the upstream issue and is reviewed before every release.

**Test: no_global_rng_leakage**

Run a fixed-seed tbsim simulation before and after unrelated NumPy random draws. Results must be identical. This catches accidental use of global NumPy RNG inside tbsim code paths.

### 11.5 Starsim Result Container Contract

**Test: result_length_matches_npts**

For every tbsim result array, length must equal the sim's number of timepoints. This catches Starsim result container changes and tbsim modules that update results at the wrong time.

**Test: result_write_once_per_step**

Use a spy result object or checksum to verify that tbsim writes each result exactly once per timestep. Double-writing can hide bugs by overwriting intermediate values.

**Test: no_nan_inf_in_public_results**

Every public result exposed by `sim.results`, `tb.results`, intervention results, and analyzer summaries must be finite unless explicitly documented as nullable. This test belongs in the fast suite.

### 11.6 Data-Integrity Invariants (Issue #1356)

These tests directly implement the fail-fast strategy proposed in Starsim issue #1356 for preventing silent UID corruption.

**Test: household_membership_invariant**

For any UID set derived from contact tracing and any index-case UID set used to generate it, assert:

`hh_ids[contact_uids] == hh_ids[index_uids]`

for the expected relationship mapping in the fixture. This invariant must run in:

- household contact tracing tests
- TPT household eligibility tests
- migration household sampling tests

**Test: uid_source_traceability**

In debug test mode, record the derivation path for UID sets used by interventions (`auids`, boolean mask + `auids`, direct UID input). Reject untraceable UID sources in critical paths.

**Test: compact_view_guardrail**

Any path that calls `np.asarray()` on a Starsim `Arr` and then uses index positions for intervention targeting must trigger a test failure unless the code explicitly maps positions back to `arr.auids`.

**Test: integrity_check_hook_smoke**

Add a lightweight integrity checker callable (test utility) that can run after each step in debug mode and verify:

- no dead UID appears in intervention output UID sets
- no UID set exceeds max raw UID unless explicitly allowed
- no duplicate UIDs in per-step targeted cohorts where uniqueness is expected

This utility is used by regression tests and contract tests, and may later be promoted into reusable diagnostics.

### 11.7 Dependency Upgrade Canary

**Test: starsim_min_version_canary**

Run the fast contract suite against the minimum supported Starsim version declared in `pyproject.toml`.

**Test: starsim_latest_version_canary**

Run the same suite against latest released Starsim. Failures here do not automatically mean tbsim is wrong, but they block dependency upgrades until reviewed.

**Test: starsim_api_surface_snapshot**

Snapshot the small set of Starsim attributes and methods tbsim relies on directly:

- `ss.Sim`
- `ss.Infection`
- `ss.Disease`
- `ss.Intervention`
- `ss.Connector`
- `ss.Product`
- `ss.Demographics`
- `ss.People`
- `ss.uids`
- Starsim array `.auids`, `.values`, and boolean masking behavior

The snapshot test should fail with a clear message if any required API disappears or changes type.

---

## Risks Covered

This section describes the specific failure modes that the test suite is designed to catch, organized by risk area.

### Risk: Silent Starsim behavior changes hiding tbsim bugs

**What can go wrong:** tbsim relies on Starsim behavior that is not fully visible from the public tbsim API: active UID handling, boolean mask semantics, module execution order, result container timing, seeded distributions, and date/rate conversion. If Starsim changes one of these behaviors, tbsim may still run and produce plausible-looking outputs while silently targeting the wrong agents, clearing flags too early, or applying rates on the wrong timestep.

The highest-risk pattern is the UID corruption footgun documented in Starsim issue #1356: converting UID-aware arrays via `np.asarray(arr)`, deriving compact alive-only positions with `np.flatnonzero` or `np.where`, then reinterpreting those positions as stable UIDs via `ss.uids(...)`.

**How the tests address it:** Phase 11 adds explicit contract tests for UID semantics, module order, time conversion, seeded distributions, result container length, finite outputs, and dedicated data-integrity invariants that fail when compact positions are treated as UIDs. The dependency matrix in Phase 0 runs those tests against both the minimum supported Starsim version and latest released Starsim. These tests are intentionally small and fail before the scientific integration tests are interpreted.

---

### Risk: Tests passing without testing meaningful behavior

**What can go wrong:** A large test suite can still be weak if many tests only assert that code runs without errors. That kind of test misses silent epidemiological bugs, incorrect flags, wrong UIDs, wrong timing, and broken stochastic behavior.

**How the tests address it:** Phase 0 requires every substantive test to use an oracle: invariant, deterministic fixture, reference calculation, differential comparison, metamorphic relation, or snapshot contract. Plotting smoke tests are the only acceptable "runs without errors" tests, and even those should inspect the created figure where possible.

---

### Risk: Agent indexing errors after population changes

**What can go wrong:** When agents die or emigrate, the mapping between a raw array position (compact index into alive-only arrays) and a stable agent UID shifts. Code that uses positional indexing into alive-only arrays — such as `arr.values[mask]` — will silently operate on the wrong agents. This is the root cause of issue #425 and is easy to re-introduce when writing new delivery or filtering code.

**How the tests address it:** Dedicated regression tests in Phase 8 cover all five sites where this bug was fixed. The general pattern — high death rate in the first 20 steps, then verifying no dead UID appears in outputs — is also applied in the UID safety tests in Phase 2 and Phase 5. Any new delivery module must add a corresponding UID safety test before being merged.

---

### Risk: Incorrect state machine transitions

**What can go wrong:** The TB model has nine states and approximately 15 distinct transitions. An off-by-one in a rate conversion (e.g., treating a per-year rate as a per-day rate, or forgetting to multiply by dt) can silently produce epidemiologically implausible outputs without raising any exceptions.

**How the tests address it:** Phase 1 covers all nine state classes, validates invariants (state sum, bounded prevalence, non-decreasing cumulative counts), and includes directional tests that confirm rate changes have the expected effect. The dt sensitivity test specifically checks that rate-per-unit-time conversions are internally consistent across coarse and fine timesteps.

---

### Risk: Intervention interactions producing incorrect results

**What can go wrong:** The rr_* modifier pattern — where TB resets all relative risk multipliers to 1.0 at the end of each step and all interventions must re-apply their effects — is easy to break. A connector or intervention that applies its modifier at the wrong point in the step order will produce no effect or a double effect, depending on timing. This is not caught by run-to-completion tests.

**How the tests address it:** Phase 2 includes explicit checks that the rr_* values on affected agents are at the expected level immediately after a step where BCG or TPT protection should be active. The combinatorial tests in Phase 7 cover cross-intervention interactions, including the case where multiple modifiers should compound multiplicatively.

---

### Risk: Cascade chain breaks

**What can go wrong:** The care cascade — health-seeking → diagnosis → treatment — depends on each upstream module setting a flag that the downstream module reads. If the flag name changes, the eligibility filter changes, or the flag reset logic fires at the wrong time, the cascade silently breaks with zero deliveries at some stage.

**How the tests address it:** Phase 6 integration tests run the full cascade end-to-end and verify that each stage produces nonzero counts. Phase 2 tests the eligibility conditions for each module independently (e.g., confirming that DxDelivery produces zero tests when `sought_care` is never set).

---

### Risk: Stochastic instability in boundary conditions

**What can go wrong:** Small populations can produce zero events in states that should be non-empty (e.g., zero diagnosed agents in a 5-step run with 50 agents), causing division-by-zero errors or silent NaN propagation in derived metrics like `incidence_kpy`.

**How the tests address it:** The population size equivalence class in Phase 7 (minimal, small, medium, large) exercises all four regimes. The `minimal` class (50 agents) is specifically designed to trigger these boundary conditions and verify that the code handles empty state arrays without errors.

---

### Risk: Household network operations on stale membership data

**What can go wrong:** The household-aware components — `HouseholdContactTracing`, `TPTHousehold`, `Migration` — all maintain or look up household membership lists. After emigration removes an agent, or after deaths, stale membership data can cause index errors or silent misattribution of contacts.

**How the tests address it:** Phase 5 includes a dedicated household UID safety test for migration. Phase 6 runs the full TPT household cascade. The regression tests in Phase 8 specifically cover the three membership-related bugs found during the migration development cycle (non-contiguous IDs, boundary ages, and empty bins).

---

### Risk: Performance regressions from vectorization changes

**What can go wrong:** The migration module had explicit performance optimization commits (f838272, 2e7107d) that replaced per-agent loops with vectorized operations. Refactoring these paths — even for correctness reasons — can easily reintroduce quadratic-time behavior that only becomes visible at scale.

**How the tests address it:** Phase 9 includes timed tests at meaningful population sizes (10,000 and 50,000 agents). The migration-specific throughput tests match the scenarios described in the optimization commits. The `migration_vectorized_hh_grouping` test is the most sensitive: assigning 1000 immigrants in a single step with a 200ms ceiling will catch any regression to the O(n) loop.

---

### Risk: CRN reproducibility breaking after refactoring

**What can go wrong:** The common random number infrastructure in starsim depends on each module drawing from its own named RNG stream. If a new code path adds an extra draw, or changes the order of draws, then simulations that previously reproduced bit-for-bit under the same seed will diverge. This breaks counterfactual comparisons and calibration workflows.

**How the tests address it:** Phase 7 includes explicit CRN reproducibility tests for the full cascade. Phase 2 includes CRN tests for `TxDelivery` in isolation. The known limitation that `ProductMulti.administer()` uses `ss.uids(np.arange(...))` and is not CRN-safe is documented, and the corresponding tests are marked as expected-failure pending the upstream fix (starsim#1254).

---

### Risk: Deleted modules re-introduced by merge conflicts

**What can go wrong:** The v0.8.0 release removed `TBAcute` and the `Immigration` class. These can be silently re-introduced by a branch merge that predates their removal.

**How the tests address it:** Phase 8 includes two guard tests that verify these names raise `AttributeError` when accessed through the `tbsim` namespace. These tests add zero overhead and run in milliseconds.

---

### Risk: Compartmental model numerical drift

**What can go wrong:** The ODE solver or the Euler-integrated `TB_SS` module can produce numerical drift — especially over long time horizons — that makes the two models diverge from each other and from the analytical steady state. This is not detected by run-to-completion tests.

**How the tests address it:** Phase 6 includes a numerical agreement test between `TB_ODE` and `TB_SS` over 50 years with a 5% tolerance. Both models must also produce finite results over 100 years (no NaN or Inf), which guards against solver divergence.

---

## Implementation Roadmap

### Phase sequence and effort

| Phase | Test Count (estimated) | Effort | Priority |
|---|---|---|---|
| 0: Test architecture and gates | 4 static tests + CI gates | Low | Critical |
| 1: Core disease model | 14 | Low | Critical |
| 2: Intervention units | 42 | Medium | Critical |
| 3: Comorbidities | 14 | Medium | High |
| 4: Analyzers and plots | 12 | Low | Medium |
| 5: Migration | 9 | Medium | High |
| 6: Integration | 11 | Medium | Critical |
| 7: Combinatorial | Generated pairwise suite + 17 fixed tests | High | High |
| 8: Regression | 12 | Low | Critical |
| 9: Performance | 10 | Medium | Medium |
| 10: System (Sim wrapper) | 9 | Low | High |
| 11: Starsim contract and canary | 20 | Medium | Critical |
| **Total** | **183+**, depending on generated pairwise rows | | |

### Prioritization

Tests marked Critical must pass before any release. Tests marked High must pass before any feature branch is merged to main. Tests marked Medium are run on a nightly schedule. Performance tests are run weekly and on release candidates.

### Suggested file organization

```
tests/
  test_test_quality.py     (Phase 0 - static checks for the test suite)
  test_tb.py              (Phase 1 - expand existing)
  test_dx_product.py      (Phase 2 - expand existing)
  test_dx_delivery.py     (Phase 2 - expand existing)
  test_tx_product.py      (Phase 2 - expand existing)
  test_tx_delivery.py     (Phase 2 - expand existing)
  test_health_seeking.py  (Phase 2 - expand existing)
  test_bcg.py             (Phase 2 - expand existing)
  test_tpt.py             (Phase 2 - expand existing)
  test_hiv.py             (Phase 3 - new)
  test_malnutrition.py    (Phase 3 - expand existing)
  test_analyzers.py       (Phase 4 - expand existing)
  test_plots.py           (Phase 4 - expand existing)
  test_migration.py       (Phase 5 - expand existing)
  test_integration.py     (Phase 6 - new)
  test_combinatorial.py   (Phase 7 - new)
  test_regression.py      (Phase 8 - consolidate regression tests)
  test_sim.py             (Phase 10 - expand existing)
  test_starsim_contract.py (Phase 11 - new)
  test_data_integrity.py  (Phase 11 - invariants and guardrails)
  data/
    pairwise_intervention_cases.csv
    starsim_uid_contract_fixture.csv
  performance/
    test_perf_sim.py      (Phase 9)
    test_perf_migration.py
    test_perf_analyzers.py
    performance_baselines.json
```

### Running the suite

```bash
# Unit and integration tests
pytest tests/ -m "not performance and not slow" --cov=tbsim --cov-report=term-missing --strict-markers -W error

# Nightly full suite
pytest tests/ -m "not performance" -n auto --strict-markers -W error

# Performance tests only
pytest tests/performance/ -m performance --tb=short

# Specific regression guard
pytest tests/test_regression.py -v

# Starsim contract checks
pytest tests/test_starsim_contract.py -v --strict-markers -W error
```

---

## Coverage Targets

| Module | Target Line Coverage |
|---|---|
| `tb.py` | 95% |
| `sim.py` | 90% |
| `interventions/*.py` | 90% |
| `comorbidities/*.py` | 85% |
| `analyzers.py` | 85% |
| `migration.py` | 90% |
| `compartmental/lshtm_ode.py` | 80% |
| `plots.py` | 75% |
| `networks.py` | 75% |
| **Overall** | **88%** |

Coverage alone is not a sufficient measure of test quality. The targets above are minimums. Tests that merely invoke code paths without asserting correctness do not count toward the meaningful coverage goal.
