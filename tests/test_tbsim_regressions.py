"""
Regression tests for known tbsim bugs and API footguns.

Each failing test maps to a TBUG-xxx entry in ``findings/bug_registry.py`` and
``findings/TBSIM_KNOWN_BUGS.md``. Run ``scripts/report_tbsim_bugs.sh`` for a
team-facing summary to file upstream issues.
"""

import numpy as np
import sciris as sc
import starsim as ss
import pytest
import tbsim
from tbsim import TBS

from findings.bug_registry import BUG_BY_TEST
from tests.test_tb import make_tb_sim

sc.options(interactive=False)


def _bug_id(test_name: str) -> str:
    return BUG_BY_TEST[test_name]["id"]


@pytest.mark.tbsim_bug
def test_dur_reinfection_protection_accepts_ss_years():
    """TBUG-001: dur_reinfection_protection must accept a bare ss.years() duration."""
    sim = tbsim.Sim(
        n_agents=300,
        sim_pars=dict(
            start=ss.date("2000-01-01"),
            stop=ss.date("2005-01-01"),
            rand_seed=1,
            verbose=0,
        ),
        tb_pars=dict(
            init_prev=ss.bernoulli(0.25),
            beta=ss.peryear(0.2),
            dur_reinfection_protection=ss.years(2),
        ),
    )
    sim.run()
    tb = sim.get_tb()
    assert len(tb.results["timevec"]) > 0, (
        f"{_bug_id('test_dur_reinfection_protection_accepts_ss_years')}: "
        "Sim with ss.years protection must complete"
    )


@pytest.mark.tbsim_bug
def test_sum_all_tb_states_equals_alive_population():
    """TBUG-002: Sum of all per-state counts must equal n_alive, not n_alive + n_DEAD."""
    sim = tbsim.Sim(
        n_agents=2_000,
        sim_pars=dict(
            start=ss.date("2000-01-01"),
            stop=ss.date("2012-01-01"),
            rand_seed=42,
            verbose=0,
        ),
        tb_pars=dict(
            init_prev=ss.bernoulli(0.25),
            beta=ss.peryear(0.4),
            sym_dead=ss.peryear(0.8),
        ),
    )
    sim.run()
    tb = sim.get_tb()

    mismatches = []
    for ti in range(len(tb.results["timevec"])):
        total_all = sum(int(tb.results[f"n_{state.name}"][ti]) for state in TBS)
        n_alive = int(sim.results.n_alive[ti])
        if total_all != n_alive:
            mismatches.append((ti, total_all, n_alive, int(tb.results["n_DEAD"][ti])))

    bug = _bug_id("test_sum_all_tb_states_equals_alive_population")
    assert not mismatches, (
        f"{bug}: sum(all n_{{state}}) must equal n_alive at every step; "
        f"found {len(mismatches)} mismatches, first={mismatches[0]}"
    )


@pytest.mark.tbsim_bug
def test_treatment_without_tx_delivery_agents_not_stuck():
    """TBUG-003: Agents in TREATMENT must not remain there without TxDelivery."""
    sim = make_tb_sim(
        n_agents=100,
        start=ss.date("2000-01-01"),
        stop=ss.date("2010-01-01"),
        pars=dict(init_prev=ss.bernoulli(0.5), beta=ss.peryear(0.0)),
    )
    sim.init()
    tb = tbsim.get_tb(sim)
    uids = ss.uids(np.arange(20))
    tb.state[uids] = TBS.TREATMENT
    tb.on_treatment[uids] = True
    tb.infected[uids] = True
    tb.susceptible[uids] = False

    sim.run()

    stuck = int((tb.state == TBS.TREATMENT).sum())
    bug = _bug_id("test_treatment_without_tx_delivery_agents_not_stuck")
    assert stuck == 0, (
        f"{bug}: agents in TREATMENT without TxDelivery must not remain stuck; "
        f"got {stuck} still in TREATMENT after a 10-year run"
    )


@pytest.mark.tbsim_bug
def test_reinfection_protection_skipped_when_rr_cleared_is_one():
    """TBUG-004: Do not schedule protection when rr_reinfection_cleared is 1.0."""
    sim = make_tb_sim(
        n_agents=80,
        pars=dict(
            beta=ss.peryear(0),
            init_prev=ss.bernoulli(0),
            inf_cle=ss.peryear(80),
            inf_non=ss.peryear(0),
            inf_asy=ss.peryear(0),
            rr_reinfection_cleared=1.0,
            dur_reinfection_protection=ss.constant(v=365),
        ),
    )
    sim.init()
    tb = tbsim.get_tb(sim)
    uids = ss.uids(np.arange(80))
    tb.state[uids] = TBS.INFECTION
    tb.infected[uids] = True
    tb.susceptible[uids] = False

    tb.step()

    cleared = uids[tb.state[uids] == TBS.CLEARED]
    assert len(cleared) > 0, "Expected INFECTION agents to clear within one step"
    scheduled = cleared[np.isfinite(tb.ti_rr_reinfection_wane[cleared])]
    bug = _bug_id("test_reinfection_protection_skipped_when_rr_cleared_is_one")
    assert len(scheduled) == 0, (
        f"{bug}: protection window must not be scheduled when rr_reinfection_cleared=1.0; "
        f"got {len(scheduled)} agents with finite ti_rr_reinfection_wane"
    )


def test_reinfection_protection_applies_rr_when_rr_cleared_below_one():
    """Control: protection mechanism works when rr_reinfection_cleared < 1."""
    rr_cleared = 0.28
    sim = make_tb_sim(
        n_agents=60,
        pars=dict(
            beta=ss.peryear(0),
            init_prev=ss.bernoulli(0),
            inf_cle=ss.peryear(80),
            inf_non=ss.peryear(0),
            inf_asy=ss.peryear(0),
            rr_reinfection_cleared=rr_cleared,
            dur_reinfection_protection=ss.constant(v=365),
        ),
    )
    sim.init()
    tb = tbsim.get_tb(sim)
    uids = ss.uids(np.arange(60))
    tb.state[uids] = TBS.INFECTION
    tb.infected[uids] = True
    tb.susceptible[uids] = False

    tb.step()

    cleared = uids[tb.state[uids] == TBS.CLEARED]
    assert len(cleared) > 0, "Expected INFECTION agents to clear within one step"
    assert np.allclose(tb.rr_reinfection[cleared], rr_cleared), (
        f"INFECTION→CLEARED must set rr_reinfection_cleared={rr_cleared}"
    )
    assert np.allclose(tb.rel_sus[cleared], rr_cleared), (
        "rel_sus on newly cleared agents must reflect rr_reinfection during protection"
    )
    assert np.all(np.isfinite(tb.ti_rr_reinfection_wane[cleared])), (
        "Finite protection window must be scheduled when rr_reinfection_cleared < 1"
    )


@pytest.mark.tbsim_bug
def test_dx_delivery_requires_hsb_sought_care_by_default():
    """TBUG-005: DxDelivery alone must not test everyone when no one sought care."""
    sim = tbsim.Sim(
        sim_pars=dict(
            n_agents=50,
            start=ss.date("2000-01-01"),
            stop=ss.date("2000-02-01"),
            dt=ss.days(7),
            rand_seed=1,
            verbose=0,
        ),
        tb_pars=dict(beta=ss.peryear(0), init_prev=ss.bernoulli(0)),
        pars=dict(interventions=[tbsim.DxDelivery(tbsim.CAD(), coverage=1.0)]),
    )
    sim.run()
    dx = next(iter(sim.interventions.values()))
    n_tested = int(np.sum(dx.results.n_tested))
    bug = _bug_id("test_dx_delivery_requires_hsb_sought_care_by_default")
    assert n_tested == 0, (
        f"{bug}: DxDelivery default eligibility must require sought_care when no "
        f"custom eligibility is supplied; got {n_tested} tests without HSB"
    )


@pytest.mark.tbsim_bug
def test_dx_product_administer_works_after_product_initialization():
    """TBUG-006: Diagnostic products must be unit-testable via administer()."""
    sim = tbsim.Sim(
        sim_pars=dict(
            n_agents=20,
            start=ss.date("2000-01-01"),
            stop=ss.date("2000-02-01"),
            dt=ss.days(7),
            rand_seed=2,
            verbose=0,
        ),
        tb_pars=dict(beta=ss.peryear(0), init_prev=ss.bernoulli(0)),
    )
    sim.init()
    tb = sim.get_tb()
    uids = sim.people.auids[:10]
    tb.state[uids] = TBS.SYMPTOMATIC
    sim.people.age[uids] = 30

    product = tbsim.Xpert()
    product.init_pre(sim)
    product.init_post()
    results = product.administer(sim, uids)

    assert set(results) == {"positive", "negative"}, (
        f"{_bug_id('test_dx_product_administer_works_after_product_initialization')}: "
        "Xpert.administer() must return positive/negative UID partitions after product init"
    )


@pytest.mark.tbsim_bug
def test_tx_product_administer_works_after_product_initialization():
    """TBUG-007: Treatment products must be unit-testable via administer()."""
    sim = tbsim.Sim(
        sim_pars=dict(
            n_agents=20,
            start=ss.date("2000-01-01"),
            stop=ss.date("2000-02-01"),
            dt=ss.days(7),
            rand_seed=3,
            verbose=0,
        ),
        tb_pars=dict(beta=ss.peryear(0), init_prev=ss.bernoulli(0)),
    )
    sim.init()
    uids = sim.people.auids[:10]

    product = tbsim.DOTS()
    product.init_pre(sim)
    product.init_post()
    results = product.administer(sim, uids)

    assert set(results) == {"success", "failure", "relapse"}, (
        f"{_bug_id('test_tx_product_administer_works_after_product_initialization')}: "
        "DOTS.administer() must return success/failure/relapse UID partitions after product init"
    )


@pytest.mark.tbsim_bug
def test_xpert_prior_tb_history_strata_are_explicit():
    """TBUG-008: Xpert scenarios must expose prior-TB-history strata explicitly."""
    product = tbsim.Xpert()
    prior_history_columns = {
        "prior_tb",
        "previous_tb",
        "recent_prior_tb",
        "years_since_tb",
        "prior_treatment",
    }
    present = prior_history_columns.intersection(set(product.df.columns))
    bug = _bug_id("test_xpert_prior_tb_history_strata_are_explicit")
    assert present, (
        f"{bug}: Xpert diagnostic table has no prior-TB-history dimension; "
        f"columns are {list(product.df.columns)}"
    )


@pytest.mark.tbsim_bug
def test_dr_tb_secondline_outputs_are_separable():
    """TBUG-009: DR-TB second-line treatment scenarios need explicit outputs."""
    dx = tbsim.DxDelivery(
        tbsim.CAD(),
        coverage=1.0,
        eligibility=lambda sim: sim.people.auids[:80],
    )
    tx = tbsim.TxDelivery(tbsim.SecondLine(dur_treatment=ss.constant(v=14)))
    sim = tbsim.Sim(
        sim_pars=dict(
            n_agents=100,
            start=ss.date("2000-01-01"),
            stop=ss.date("2000-06-01"),
            dt=ss.days(7),
            rand_seed=4,
            verbose=0,
        ),
        tb_pars=dict(beta=ss.peryear(0), init_prev=ss.bernoulli(0)),
        pars=dict(interventions=[dx, tx]),
    )
    sim.init()
    tb = sim.get_tb()
    uids = sim.people.auids[:80]
    tb.state[uids] = TBS.SYMPTOMATIC
    tb.susceptible[uids] = False
    tb.infected[uids] = True
    sim.run()

    tx = next(i for i in sim.interventions.values() if isinstance(i, tbsim.TxDelivery))
    result_keys = set(tx.results.keys())
    separable = any(
        token in key.lower()
        for key in result_keys
        for token in ["dr", "mdr", "resistant", "secondline", "second_line"]
    )
    bug = _bug_id("test_dr_tb_secondline_outputs_are_separable")
    assert separable, (
        f"{bug}: SecondLine treatment outcomes are only reported through generic "
        f"TxDelivery result keys {sorted(result_keys)}"
    )


if __name__ == "__main__":
    pytest.main(["-x", "-v", __file__])
