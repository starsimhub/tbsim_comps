"""
Registry of known upstream tbsim defects tracked by this harness.

Each entry maps to one pytest in ``tests/test_tbsim_regressions.py``. When the test
passes, update ``status`` to ``fixed`` and record ``fixed_in``.
"""

from __future__ import annotations

BUGS: list[dict] = [
    {
        "id": "TBUG-001",
        "title": "dur_reinfection_protection duration input crashes mid-run",
        "severity": "high",
        "status": "open",
        "test": "test_dur_reinfection_protection_accepts_ss_years",
        "module": "tbsim.tb",
        "symptom": (
            "Passing ``dur_reinfection_protection=ss.years(2)`` raises "
            "``AttributeError: 'years' object has no attribute 'rvs'`` mid-run."
        ),
        "expected": (
            "Either accept bare Starsim durations (coerce to ``ss.constant(v=...)``) "
            "or validate at ``TB.__init__`` with a clear error naming the parameter."
        ),
        "repro": (
            "tbsim.Sim(tb_pars=dict(dur_reinfection_protection=ss.years(2), "
            "init_prev=ss.bernoulli(0.25), beta=ss.peryear(0.2))).run()"
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
]

OPEN_BUGS = [b for b in BUGS if b["status"] == "open"]

BUG_BY_TEST = {b["test"]: b for b in BUGS}
