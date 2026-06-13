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
]

OPEN_BUGS = [b for b in BUGS if b["status"] == "open"]

BUG_BY_TEST = {b["test"]: b for b in BUGS}
