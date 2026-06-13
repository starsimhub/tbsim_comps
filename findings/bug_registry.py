"""
Registry of known upstream tbsim defects tracked by this harness.

Each entry maps to one pytest in ``tests/test_tbsim_regressions.py``. When the test
passes, update ``status`` to ``fixed`` and record ``fixed_in``.
"""

from __future__ import annotations

BUGS: list[dict] = [
    {
        "id": "TBUG-001",
        "title": "dur_reinfection_protection crashes on ss.years()",
        "severity": "high",
        "status": "open",
        "test": "test_dur_reinfection_protection_accepts_ss_years",
        "module": "tbsim.tb",
        "symptom": (
            "Passing ``dur_reinfection_protection=ss.years(2)`` raises "
            "``AttributeError: 'years' object has no attribute 'rvs'`` mid-run."
        ),
        "expected": (
            "Accept bare Starsim durations (coerce to ``ss.constant(v=...)``) or "
            "validate at ``TB.__init__`` with a clear error."
        ),
        "repro": (
            "tbsim.Sim(tb_pars=dict(dur_reinfection_protection=ss.years(2), "
            "init_prev=ss.bernoulli(0.25), beta=ss.peryear(0.2))).run()"
        ),
    },
    {
        "id": "TBUG-002",
        "title": "Per-state counts do not partition alive population",
        "severity": "medium",
        "status": "open",
        "test": "test_sum_all_tb_states_equals_alive_population",
        "module": "tbsim.tb",
        "symptom": (
            "``sum(n_{state} for state in TBS)`` exceeds ``n_alive`` whenever "
            "``n_DEAD > 0``; terminal agents are double-counted in results."
        ),
        "expected": (
            "Either exclude non-alive DEAD/REMOVED from ``n_{state}`` snapshots, "
            "or document that only non-terminal states sum to ``n_alive``."
        ),
        "repro": (
            "Run with ``sym_dead=ss.peryear(0.8)``; compare "
            "``sum(tb.results[f'n_{s.name}'][ti])`` to ``sim.results.n_alive[ti]``."
        ),
    },
    {
        "id": "TBUG-003",
        "title": "TREATMENT state permanent without TxDelivery",
        "severity": "medium",
        "status": "open",
        "test": "test_treatment_without_tx_delivery_agents_not_stuck",
        "module": "tbsim.tb",
        "symptom": (
            "Agents placed in ``TREATMENT`` never leave that state if no "
            "``TxDelivery`` intervention is attached."
        ),
        "expected": (
            "Natural-history exit from TREATMENT, a startup validation error when "
            "TREATMENT is populated without TxDelivery, or documented API guard."
        ),
        "repro": (
            "Set ``tb.state[uids] = TBS.TREATMENT`` after ``sim.init()``; run 10y "
            "with no TxDelivery; agents remain in TREATMENT."
        ),
    },
    {
        "id": "TBUG-004",
        "title": "No-op reinfection protection scheduled when rr_cleared is 1.0",
        "severity": "low",
        "status": "open",
        "test": "test_reinfection_protection_skipped_when_rr_cleared_is_one",
        "module": "tbsim.tb",
        "symptom": (
            "INFECTION→CLEARED sets finite ``ti_rr_reinfection_wane`` even when "
            "``rr_reinfection_cleared=1.0``, so protection windows have no effect."
        ),
        "expected": (
            "Skip scheduling when ``rr_reinfection_cleared >= 1.0``, or lower the "
            "default ``rr_reinfection_cleared`` when protection duration is set."
        ),
        "repro": (
            "Force INFECTION→CLEARED with ``dur_reinfection_protection=ss.constant(365)`` "
            "and default ``rr_reinfection_cleared=1.0``; cleared agents get finite wane times."
        ),
    },
    {
        "id": "TBUG-005",
        "title": "DxDelivery tests all alive agents when HealthSeekingBehavior is absent",
        "severity": "high",
        "status": "open",
        "test": "test_dx_delivery_requires_hsb_sought_care_by_default",
        "module": "tbsim.interventions.diagnostics",
        "symptom": (
            "A default ``DxDelivery`` with no ``HealthSeekingBehavior`` tests every "
            "alive agent each step because ``_get_eligible()`` falls back to all alive."
        ),
        "expected": (
            "Default eligibility should require ``sought_care`` or fail loudly when "
            "the HSB dependency is missing; mass screening should require explicit "
            "custom eligibility."
        ),
        "repro": (
            "Run ``tbsim.Sim`` with only ``DxDelivery(CAD(), coverage=1.0)`` and no HSB; "
            "``sum(dx.results.n_tested)`` is nonzero."
        ),
    },
    {
        "id": "TBUG-006",
        "title": "Diagnostic products cannot be administered in isolation after init",
        "severity": "medium",
        "status": "open",
        "test": "test_dx_product_administer_works_after_product_initialization",
        "module": "tbsim.interventions.diagnostics",
        "symptom": (
            "Calling ``Xpert().administer(sim, uids)`` after ``init_pre/init_post`` "
            "raises ``DistNotInitializedError`` from an internal ``choice2d`` draw."
        ),
        "expected": (
            "Diagnostic products should be directly unit-testable after standard product "
            "initialization, or expose a documented initialization helper for administer()."
        ),
        "repro": (
            "Initialize a small ``tbsim.Sim``, call ``product = Xpert(); "
            "product.init_pre(sim); product.init_post(); product.administer(sim, uids)``."
        ),
    },
    {
        "id": "TBUG-007",
        "title": "Treatment products cannot be administered in isolation after init",
        "severity": "medium",
        "status": "open",
        "test": "test_tx_product_administer_works_after_product_initialization",
        "module": "tbsim.interventions.treatments",
        "symptom": (
            "Calling ``DOTS().administer(sim, uids)`` after ``init_pre/init_post`` "
            "raises ``DistNotInitializedError`` from internal Bernoulli distributions."
        ),
        "expected": (
            "Treatment products should be directly unit-testable after standard product "
            "initialization, or expose a documented initialization helper for administer()."
        ),
        "repro": (
            "Initialize a small ``tbsim.Sim``, call ``product = DOTS(); "
            "product.init_pre(sim); product.init_post(); product.administer(sim, uids)``."
        ),
    },
    {
        "id": "TBUG-008",
        "title": "Xpert diagnostic scenarios lack prior-TB-history stratification",
        "severity": "medium",
        "status": "open",
        "test": "test_xpert_prior_tb_history_strata_are_explicit",
        "module": "tbsim.interventions.diagnostics",
        "symptom": (
            "``Xpert`` probability tables stratify by age and TB state but have no "
            "dimension for prior TB, recent prior TB, or previous treatment history."
        ),
        "expected": (
            "Diagnostic scenarios that use prior-treatment history should expose an "
            "explicit table dimension or scenario flag so assumptions are not silent."
        ),
        "repro": (
            "Inspect ``tbsim.Xpert().df.columns``; no prior-TB-history column exists."
        ),
    },
    {
        "id": "TBUG-009",
        "title": "DR-TB second-line treatment outputs are not separable",
        "severity": "medium",
        "status": "open",
        "test": "test_dr_tb_secondline_outputs_are_separable",
        "module": "tbsim.interventions.treatments",
        "symptom": (
            "``SecondLine`` treatment can be delivered, but outcomes are reported only "
            "through generic ``TxDelivery`` result names, with no DR/MDR/resistance-specific "
            "state or output channel."
        ),
        "expected": (
            "DR-TB scenarios should have explicit assumption flags and separable outputs "
            "so drug-resistant and drug-susceptible treatment outcomes are not conflated."
        ),
        "repro": (
            "Run ``TxDelivery(SecondLine())`` and inspect ``tx.results.keys()``; only "
            "generic treatment result channels are present."
        ),
    },
]

OPEN_BUGS = [b for b in BUGS if b["status"] == "open"]

BUG_BY_TEST = {b["test"]: b for b in BUGS}
