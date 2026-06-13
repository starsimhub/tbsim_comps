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


if __name__ == "__main__":
    pytest.main(["-x", "-v", __file__])
