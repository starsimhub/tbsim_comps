"""
Phase 1 tests for the core TB disease model (tbsim.TB / TBS).

Covers:
  1.1 Equivalent classes for TB agent state
  1.2 State machine invariants
  1.3 Transition rate sensitivity
  1.4 Initialization
  1.5 Death handling
  1.6 dt sensitivity

Run as pytest or as a standalone script:
    python tests/test_tb.py
"""

import numpy as np
import sciris as sc
import starsim as ss
import matplotlib.pyplot as plt
import pytest
import tbsim
from tbsim import TBS

n_agents = 500
do_plot  = False
sc.options(interactive=False)


# =============================================================================
# Shared fixture
# =============================================================================

def make_tb_sim(
    n_agents=100,
    start=ss.date("2000-01-01"),
    stop=ss.date("2010-12-31"),
    dt=ss.days(7),
    pars=None,
    **kwargs,
):
    """Build a minimal Sim containing only TB (no demographics, no other diseases)."""
    tb  = tbsim.TB(pars=pars)
    net = ss.RandomNet(pars=dict(n_contacts=ss.poisson(lam=5), dur=30))
    sim = ss.Sim(
        n_agents=n_agents, networks=net, diseases=tb,
        dt=dt, start=start, stop=stop, **kwargs,
    )
    sim.pars.verbose = 0
    return sim


# =============================================================================
# 1.1 / 1.2 — State machine invariants and equivalent classes
# (ported from the reference test suite; assertions are unchanged)
# =============================================================================

def test_transition_empty_uids():
    """transition() with empty uid array must not raise."""
    sim = make_tb_sim(n_agents=10)
    sim.init()
    tb = tbsim.get_tb(sim)
    tb.transition(np.array([], dtype=int), to={
        TBS.CLEARED: tb.pars.inf_cle,
        TBS.NON_INFECTIOUS: tb.pars.inf_non,
    }, rng=tb._rng_inf)


def test_transition_sets_valid_states():
    """transition() assigns agents to exactly the destination states supplied."""
    sim = make_tb_sim(n_agents=500)
    sim.init()
    tb  = tbsim.get_tb(sim)
    uids = ss.uids(np.arange(500))
    tb.state[uids] = TBS.INFECTION
    keys = [TBS.CLEARED, TBS.NON_INFECTIOUS, TBS.ASYMPTOMATIC]
    tb.transition(uids, to={
        TBS.CLEARED:        tb.pars.inf_cle,
        TBS.NON_INFECTIOUS: tb.pars.inf_non,
        TBS.ASYMPTOMATIC:   tb.pars.inf_asy,
    }, rng=tb._rng_inf)
    transitioned = uids[np.isin(tb.state[uids], keys)]
    assert len(transitioned) > 0, "With 500 agents and typical rates, some should transition"


def test_set_prognoses_sets_state_and_susceptible():
    """set_prognoses() puts agents in INFECTION and clears susceptible flag."""
    sim = make_tb_sim(n_agents=50)
    sim.init()
    tb  = tbsim.get_tb(sim)
    uids = ss.uids([1, 2, 3, 10, 20])
    tb.susceptible[uids] = True
    tb.infected[uids]    = False
    tb.set_prognoses(uids)
    assert np.all(tb.state[uids] == TBS.INFECTION)
    assert not tb.susceptible[uids].any()
    assert tb.infected[uids].all()
    assert tb.ever_infected[uids].all()
    assert np.all(tb.ti_infected[uids] == tb.ti)


def test_set_prognoses_empty_uids():
    """set_prognoses() with empty uid array must not raise."""
    sim = make_tb_sim(n_agents=10)
    sim.init()
    tb  = tbsim.get_tb(sim)
    tb.set_prognoses(np.array([], dtype=int))


def test_step_die():
    """step_die() sets state=DEAD and clears susceptible, infected, rel_trans."""
    sim = make_tb_sim(n_agents=50)
    sim.init()
    tb  = tbsim.get_tb(sim)
    uids = ss.uids([1, 2, 3])
    tb.susceptible[uids] = True
    tb.infected[uids]    = True
    tb.rel_trans[uids]   = 1.0
    tb.state[uids]       = TBS.SYMPTOMATIC
    tb.step_die(uids)
    assert not tb.susceptible[uids].any(), "step_die must clear susceptible"
    assert not tb.infected[uids].any(),    "step_die must clear infected"
    assert (tb.rel_trans[uids] == 0).all(), "step_die must zero rel_trans"
    assert np.all(tb.state[uids] == TBS.DEAD), "step_die must set state=DEAD"


def test_step_die_empty_uids():
    """step_die() with empty uid array must not raise."""
    sim = make_tb_sim(n_agents=10)
    sim.init()
    tb  = tbsim.get_tb(sim)
    tb.step_die(np.array([], dtype=int))


def test_sim_run_tb():
    """A short simulation with TB runs and returns the expected result keys."""
    sim = make_tb_sim(
        n_agents=200,
        start=ss.date("2000-01-01"),
        stop=ss.date("2002-12-31"),
        pars={"init_prev": ss.bernoulli(0.05), "beta": ss.peryear(0.2)},
    )
    sim.run()
    tb = tbsim.get_tb(sim)
    for key in ("n_infectious", "prevalence_active", "incidence_kpy",
                "new_deaths", "cum_active"):
        assert key in tb.results, f"Expected result key '{key}' to be present"
    assert len(tb.results["timevec"]) > 0
    assert np.any(np.isfinite(tb.results["prevalence_active"][:]))


def test_init_results_defines_expected_keys():
    """init_results() registers per-state counts and all top-level outcome series."""
    sim = make_tb_sim(n_agents=30)
    sim.init()
    tb  = tbsim.get_tb(sim)
    for state in TBS:
        assert f"n_{state.name}"      in tb.results
        assert f"n_{state.name}_15+"  in tb.results
    for key in ("n_infectious", "new_active", "cum_active", "new_deaths",
                "cum_deaths", "prevalence_active", "incidence_kpy",
                "new_notifications_15+", "n_detectable_15+"):
        assert key in tb.results, f"Expected result key '{key}'"


def test_finalize_results_cumulative():
    """finalize_results() must make cum_deaths and cum_active equal cumsum of new_*."""
    sim = make_tb_sim(n_agents=50, start=ss.date("2000-01-01"), stop=ss.date("2001-12-31"))
    sim.run()
    tb  = tbsim.get_tb(sim)
    tb.finalize_results()
    np.testing.assert_array_equal(
        np.cumsum(tb.results["new_deaths"][:]), tb.results["cum_deaths"][:],
        err_msg="cum_deaths must equal cumsum of new_deaths",
    )
    np.testing.assert_array_equal(
        np.cumsum(tb.results["new_active"][:]), tb.results["cum_active"][:],
        err_msg="cum_active must equal cumsum of new_active",
    )


def test_plot_returns_figure():
    """TB.plot() must return a non-None matplotlib Figure."""
    sim = make_tb_sim(n_agents=50, start=ss.date("2000-01-01"), stop=ss.date("2001-12-31"))
    sim.run()
    fig = tbsim.get_tb(sim).plot(show=False)
    assert fig is not None
    assert isinstance(fig, plt.Figure), "plot() must return a matplotlib Figure"


def test_state_counts_sum_to_population():
    """Sum of per-state counts must equal the live population at t=0 and t=final."""
    sim = make_tb_sim(n_agents=150, start=ss.date("2000-01-01"), stop=ss.date("2003-12-31"))
    sim.run()
    tb = tbsim.get_tb(sim)
    n_now         = len(tb.sim.people)
    total_final   = sum(tb.results[f"n_{s.name}"][-1] for s in TBS)
    total_initial = sum(tb.results[f"n_{s.name}"][0]  for s in TBS)
    assert total_final == n_now, (
        f"Final state counts sum to {total_final}, expected {n_now}"
    )
    assert total_initial == 150, (
        f"Initial state counts sum to {total_initial}, expected 150"
    )


def test_n_infectious_matches_infectious_states():
    """n_infectious result must equal live count of ASYMPTOMATIC | SYMPTOMATIC at final step."""
    sim = make_tb_sim(n_agents=100, start=ss.date("2000-01-01"), stop=ss.date("2002-12-31"))
    sim.run()
    tb  = tbsim.get_tb(sim)
    ti  = tb.ti
    expected = np.count_nonzero(
        (tb.state == TBS.ASYMPTOMATIC) | (tb.state == TBS.SYMPTOMATIC)
    )
    tb.update_results()
    assert tb.results["n_infectious"][ti] == expected, (
        f"n_infectious={tb.results['n_infectious'][ti]}, "
        f"direct count={expected}"
    )


def test_prevalence_active_in_valid_range():
    """prevalence_active must stay in [0, 1] at every finite timestep."""
    sim = make_tb_sim(n_agents=200, start=ss.date("2000-01-01"), stop=ss.date("2005-12-31"))
    sim.run()
    tb  = tbsim.get_tb(sim)
    for ti, prev in enumerate(tb.results["prevalence_active"][:]):
        if np.isfinite(prev):
            assert 0 <= prev <= 1, f"prevalence_active at ti={ti} out of [0,1]: {prev}"


def test_cumulative_series_non_decreasing():
    """cum_deaths and cum_active must be non-decreasing over the full run."""
    sim = make_tb_sim(n_agents=200, start=ss.date("2000-01-01"), stop=ss.date("2004-12-31"))
    sim.run()
    tb  = tbsim.get_tb(sim)
    assert np.all(np.diff(tb.results["cum_deaths"][:]) >= 0), "cum_deaths must be non-decreasing"
    assert np.all(np.diff(tb.results["cum_active"][:]) >= 0), "cum_active must be non-decreasing"


def test_new_events_non_negative():
    """new_deaths, new_active, and new_notifications_15+ must be non-negative."""
    sim = make_tb_sim(n_agents=150, start=ss.date("2000-01-01"), stop=ss.date("2003-12-31"))
    sim.run()
    tb  = tbsim.get_tb(sim)
    assert np.all(tb.results["new_deaths"][:]              >= 0), "new_deaths has negative values"
    assert np.all(tb.results["new_active"][:]              >= 0), "new_active has negative values"
    assert np.all(tb.results["new_notifications_15+"][:] >= 0), "new_notifications_15+ has negative values"


def test_susceptible_only_cleared_or_never_infected():
    """susceptible flag must be True only for SUSCEPTIBLE or CLEARED state agents."""
    sim = make_tb_sim(n_agents=80, start=ss.date("2000-01-01"), stop=ss.date("2002-12-31"))
    sim.run()
    tb  = tbsim.get_tb(sim)
    susceptible_states = {TBS.SUSCEPTIBLE, TBS.CLEARED}
    for i in range(len(tb.state)):
        if tb.susceptible[i]:
            assert tb.state[i] in susceptible_states, (
                f"Agent {i} susceptible but in state={tb.state[i]}"
            )
        else:
            assert tb.state[i] not in susceptible_states, (
                f"Agent {i} not susceptible but state={tb.state[i]} is a susceptible state"
            )


def test_rel_sus_rel_trans_after_step():
    """CLEARED agents carry rr_reinfection as rel_sus; ASYMPTOMATIC carry trans_asymp as rel_trans."""
    sim = make_tb_sim(n_agents=60)
    sim.run()
    tb  = tbsim.get_tb(sim)
    cleared_uids = ss.uids(tb.state == TBS.CLEARED)
    asymp_uids   = ss.uids(tb.state == TBS.ASYMPTOMATIC)
    if len(cleared_uids) > 0:
        assert np.allclose(tb.rel_sus[cleared_uids], tb.rr_reinfection[cleared_uids]), (
            "CLEARED agents must have rel_sus == rr_reinfection"
        )
    if len(asymp_uids) > 0:
        assert np.allclose(tb.rel_trans[asymp_uids], tb.pars.trans_asymp), (
            "ASYMPTOMATIC agents must have rel_trans == trans_asymp"
        )


def test_transition_single_destination():
    """All agents that leave INFECTION must arrive at the single destination state."""
    sim = make_tb_sim(n_agents=200)
    sim.init()
    tb  = tbsim.get_tb(sim)
    uids = ss.uids(np.arange(200))
    tb.state[uids] = TBS.INFECTION
    tb.transition(uids, to={TBS.CLEARED: tb.pars.inf_cle}, rng=tb._rng_inf)
    transitioned = uids[tb.state[uids] == TBS.CLEARED]
    assert len(transitioned) > 0, "With 200 agents and typical rates, some should reach CLEARED"


def test_step_all_susceptible_no_infection_leaves_state_unchanged():
    """With init_prev=0 and beta=0, step() must leave all agent states unchanged."""
    sim = make_tb_sim(
        n_agents=40,
        pars={"init_prev": ss.bernoulli(0.0), "beta": ss.peryear(0.0)},
    )
    sim.init()
    tb   = tbsim.get_tb(sim)
    before = np.array(tb.state, copy=True)
    tb.step()
    np.testing.assert_array_equal(before, np.array(tb.state),
        err_msg="step() changed agent states when no transmission is possible")


def test_rr_activation_zero_prevents_progression_to_active():
    """With rr_activation=0, INFECTION agents can only transition to CLEARED (not active states)."""
    sim = make_tb_sim(n_agents=200)
    sim.init()
    tb  = tbsim.get_tb(sim)
    uids = ss.uids(np.arange(200))
    tb.state[uids]         = TBS.INFECTION
    tb.rr_activation[uids] = 0
    tb.transition(uids, to={
        TBS.CLEARED:        tb.pars.inf_cle,
        TBS.NON_INFECTIOUS: tb.pars.inf_non * tb.rr_activation[uids],
        TBS.ASYMPTOMATIC:   tb.pars.inf_asy * tb.rr_activation[uids],
    }, rng=tb._rng_inf)
    transitioned = uids[tb.state[uids] != TBS.INFECTION]
    assert len(transitioned) > 0, "Some agents should have transitioned"
    assert np.all(tb.state[transitioned] == TBS.CLEARED), (
        "With rr_activation=0, all transitioners must go to CLEARED"
    )


def test_zero_beta_no_initial_infection_no_transmission():
    """With init_prev=0 and beta=0, no transmission occurs over the full run."""
    sim = make_tb_sim(
        n_agents=80,
        start=ss.date("2000-01-01"),
        stop=ss.date("2001-12-31"),
        pars={"init_prev": ss.bernoulli(0.0), "beta": ss.peryear(0.0)},
    )
    sim.run()
    tb = tbsim.get_tb(sim)
    assert np.all(tb.state == TBS.SUSCEPTIBLE), "All agents must stay SUSCEPTIBLE"
    assert not tb.infected.any()
    assert tb.results["cum_active"][-1] == 0,  "cum_active must stay 0"
    assert tb.results["cum_deaths"][-1] == 0,  "cum_deaths must stay 0"


def test_detectable_15_plus_bounds():
    """n_detectable_15+ must be bounded by n_SYMPTOMATIC_15+ + n_ASYMPTOMATIC_15+ at every step."""
    sim = make_tb_sim(n_agents=100, start=ss.date("2000-01-01"), stop=ss.date("2002-12-31"))
    sim.run()
    tb  = tbsim.get_tb(sim)
    for ti in range(len(tb.results["timevec"])):
        upper = tb.results["n_SYMPTOMATIC_15+"][ti] + tb.results["n_ASYMPTOMATIC_15+"][ti]
        det   = tb.results["n_detectable_15+"][ti]
        assert 0 <= det <= upper + 1e-6, (
            f"n_detectable_15+ at ti={ti}: {det} exceeds upper bound {upper}"
        )


def test_on_treatment_consistent_with_state():
    """on_treatment flag must exactly match (state == TREATMENT) at end of run."""
    sim = make_tb_sim(n_agents=120, start=ss.date("2000-01-01"), stop=ss.date("2004-12-31"))
    sim.run()
    tb  = tbsim.get_tb(sim)
    np.testing.assert_array_equal(
        tb.on_treatment, (tb.state == TBS.TREATMENT),
        err_msg="on_treatment must equal (state == TREATMENT)",
    )


def test_rr_reinfection_waning():
    """Agents past their protection window must revert to rr_reinfection=1.0."""
    sim = make_tb_sim(
        n_agents=200,
        start=ss.date("2000-01-01"),
        stop=ss.date("2005-12-31"),
        pars={
            "init_prev":                  ss.bernoulli(0.3),
            "beta":                       ss.peryear(0.5),
            "dur_reinfection_protection": ss.constant(v=365),
            "rr_reinfection_rec":         0.21,
        },
    )
    sim.run()
    tb      = tbsim.get_tb(sim)
    cleared = ss.uids(tb.state == TBS.CLEARED)
    assert len(cleared) > 0, "Expected CLEARED agents after 5-year run"
    waned   = cleared[tb.ti >= tb.ti_rr_reinfection_wane[cleared]]
    if len(waned) > 0:
        assert np.allclose(tb.rr_reinfection[waned], 1.0), (
            "Agents past protection window must have rr_reinfection=1.0"
        )
        assert np.all(tb.ti_rr_reinfection_wane[waned] == np.inf), (
            "Waned agents must have ti_rr_reinfection_wane=inf"
        )
    return sim


# =============================================================================
# 1.3 — Transition rate sensitivity
# =============================================================================

@sc.timer()
def test_higher_beta_higher_prevalence(do_plot=do_plot):
    """Higher beta must produce higher mean active-TB prevalence (1.3)."""
    sc.heading('Testing higher beta → higher prevalence...')
    common    = dict(n_agents=n_agents, start=ss.date('2000-01-01'), stop=ss.date('2008-12-31'))
    base_pars = dict(init_prev=ss.bernoulli(0.15))
    sim_lo = make_tb_sim(**common, pars={**base_pars, 'beta': ss.peryear(0.1)})
    sim_hi = make_tb_sim(**common, pars={**base_pars, 'beta': ss.peryear(0.6)})
    for sim in (sim_lo, sim_hi):
        sim.pars.rand_seed = 42
    sim_lo.run(); sim_hi.run()
    prev_lo = float(np.mean(tbsim.get_tb(sim_lo).results['prevalence_active'][:]))
    prev_hi = float(np.mean(tbsim.get_tb(sim_hi).results['prevalence_active'][:]))
    assert prev_hi > prev_lo, (
        f'Higher beta should raise mean prevalence; '
        f'got hi={prev_hi:.4f} vs lo={prev_lo:.4f}'
    )
    if do_plot:
        plt.figure()
        plt.plot(tbsim.get_tb(sim_lo).results['prevalence_active'][:], label='low beta')
        plt.plot(tbsim.get_tb(sim_hi).results['prevalence_active'][:], label='high beta')
        plt.legend(); plt.title('Higher beta → higher prevalence')
    return sim_hi


@sc.timer()
def test_higher_activation_rate_more_active_earlier(do_plot=do_plot):
    """Higher inf_non/inf_asy must produce more cumulative active cases (1.3)."""
    sc.heading('Testing higher activation rate → more active cases...')
    common    = dict(n_agents=n_agents, start=ss.date('2000-01-01'), stop=ss.date('2005-12-31'))
    base_pars = dict(init_prev=ss.bernoulli(0.30), beta=ss.peryear(0.0))
    slow = {**base_pars, 'inf_non': ss.peryear(0.05), 'inf_asy': ss.peryear(0.05)}
    fast = {**base_pars, 'inf_non': ss.peryear(2.0),  'inf_asy': ss.peryear(2.0)}
    sim_slow = make_tb_sim(**common, pars=slow)
    sim_fast = make_tb_sim(**common, pars=fast)
    for sim in (sim_slow, sim_fast):
        sim.pars.rand_seed = 7
    sim_slow.run(); sim_fast.run()
    cum_slow = tbsim.get_tb(sim_slow).results['cum_active'][-1]
    cum_fast = tbsim.get_tb(sim_fast).results['cum_active'][-1]
    assert cum_fast > cum_slow, (
        f'Faster activation should raise cum_active; '
        f'got fast={cum_fast} vs slow={cum_slow}'
    )
    return sim_fast


@sc.timer()
def test_higher_clearance_rate_lower_prevalence(do_plot=do_plot):
    """Higher non_rec/asy_non must reduce mean active-TB prevalence (1.3)."""
    sc.heading('Testing higher clearance rate → lower prevalence...')
    common    = dict(n_agents=n_agents, start=ss.date('2000-01-01'), stop=ss.date('2006-12-31'))
    base_pars = dict(init_prev=ss.bernoulli(0.20), beta=ss.peryear(0.3))
    low_clr  = {**base_pars, 'non_rec': ss.peryear(0.05), 'asy_non': ss.peryear(0.05)}
    high_clr = {**base_pars, 'non_rec': ss.peryear(5.0),  'asy_non': ss.peryear(5.0)}
    sim_lo = make_tb_sim(**common, pars=low_clr)
    sim_hi = make_tb_sim(**common, pars=high_clr)
    for sim in (sim_lo, sim_hi):
        sim.pars.rand_seed = 13
    sim_lo.run(); sim_hi.run()
    prev_lo = float(np.mean(tbsim.get_tb(sim_lo).results['prevalence_active'][:]))
    prev_hi = float(np.mean(tbsim.get_tb(sim_hi).results['prevalence_active'][:]))
    assert prev_hi < prev_lo, (
        f'Higher clearance should lower mean prevalence; '
        f'got high_clr={prev_hi:.4f} vs low_clr={prev_lo:.4f}'
    )
    return sim_hi


@sc.timer()
def test_rr_death_multiplicative(do_plot=do_plot):
    """A much higher sym_dead rate must produce more cumulative deaths (1.3).

    rr_death is per-step, so we compare two sims that differ in sym_dead by a
    large factor. The directional assertion is non-flaky because the factor is ~50x.
    """
    sc.heading('Testing higher sym_dead → more deaths...')
    common    = dict(n_agents=1_000, start=ss.date('2000-01-01'), stop=ss.date('2010-12-31'))
    base_pars = dict(init_prev=ss.bernoulli(0.30), beta=ss.peryear(0.3))
    sim_base = make_tb_sim(**common, pars={**base_pars, 'sym_dead': ss.peryear(0.1)})
    sim_high = make_tb_sim(**common, pars={**base_pars, 'sym_dead': ss.peryear(5.0)})
    for sim in (sim_base, sim_high):
        sim.pars.rand_seed = 99
    sim_base.run(); sim_high.run()
    d_base = tbsim.get_tb(sim_base).results['cum_deaths'][-1]
    d_high = tbsim.get_tb(sim_high).results['cum_deaths'][-1]
    assert d_high > d_base, (
        f'50x higher sym_dead should raise cum_deaths; '
        f'got high={d_high} vs base={d_base}'
    )
    return sim_high


# =============================================================================
# 1.4 — Initialization
# =============================================================================

@sc.timer()
def test_init_prev_respected():
    """Infected count at t=0 must be within 3 SDs of init_prev * n (1.4)."""
    sc.heading('Testing init_prev is respected at t=0...')
    p, n = 0.20, 2_000
    sim  = make_tb_sim(n_agents=n, pars={'init_prev': ss.bernoulli(p)})
    sim.init()
    tb         = tbsim.get_tb(sim)
    n_infected = int(tb.infected.sum())
    sd         = (n * p * (1 - p)) ** 0.5
    assert p * n - 3 * sd <= n_infected <= p * n + 3 * sd, (
        f'Infected count {n_infected} outside 3-SD range '
        f'[{p*n - 3*sd:.0f}, {p*n + 3*sd:.0f}] for init_prev={p}, n={n}'
    )
    return sim


@sc.timer()
def test_init_state_distribution():
    """INFECTION, ASYMPTOMATIC, and SYMPTOMATIC must all appear within a 3-year run (1.4).

    At t=0 only INFECTION is populated. Progression must fill the active substates
    within a few years even without new transmissions.
    """
    sc.heading('Testing disease substates populate after init...')
    sim = make_tb_sim(
        n_agents=2_000,
        start=ss.date('2000-01-01'),
        stop=ss.date('2003-12-31'),
        pars={'init_prev': ss.bernoulli(0.50), 'beta': ss.peryear(0.0)},
    )
    sim.run()
    tb = tbsim.get_tb(sim)
    for state in [TBS.INFECTION, TBS.ASYMPTOMATIC, TBS.SYMPTOMATIC]:
        total = int(tb.results[f'n_{state.name}'][:].sum())
        assert total > 0, (
            f'State {state.name} was never populated during a 3-year run '
            f'with init_prev=0.5 and 2000 agents'
        )
    return sim


# =============================================================================
# 1.5 — Death handling
# =============================================================================

@sc.timer()
def test_step_die_updates_flags_and_state():
    """step_die() must mark targeted agents DEAD and clear all active flags (1.5)."""
    sc.heading('Testing step_die clears flags and sets DEAD...')
    sim  = make_tb_sim(n_agents=50)
    sim.init()
    tb   = tbsim.get_tb(sim)
    uids = ss.uids([5, 10, 15, 20])
    tb.state[uids]       = TBS.SYMPTOMATIC
    tb.susceptible[uids] = False
    tb.infected[uids]    = True
    tb.rel_trans[uids]   = 1.0
    tb.step_die(uids)
    assert np.all(tb.state[uids] == TBS.DEAD),     "step_die must set state=DEAD"
    assert not tb.susceptible[uids].any(),          "step_die must clear susceptible"
    assert not tb.infected[uids].any(),             "step_die must clear infected"
    assert (tb.rel_trans[uids] == 0).all(),         "step_die must zero rel_trans"
    return sim


@sc.timer()
def test_dead_agents_ejected_from_population():
    """TB deaths must be recorded in results and the dead agents fully removed (1.5).

    In tbsim, agents that die from TB disease are ejected from ss.People (the
    population array compresses). After the run TBS.DEAD must never appear in
    tb.state, and the cumulative death count must be non-zero.
    """
    sc.heading('Testing dead agents are ejected from active state...')
    sim = make_tb_sim(
        n_agents=1_000,
        start=ss.date('2000-01-01'),
        stop=ss.date('2010-12-31'),
        pars=dict(
            init_prev=ss.bernoulli(0.50),
            beta=ss.peryear(0.3),
            sym_dead=ss.peryear(2.0),
        ),
    )
    sim.run()
    tb         = tbsim.get_tb(sim)
    cum_deaths = float(tb.results['cum_deaths'][-1])
    assert cum_deaths > 0, (
        f'Expected TB deaths with sym_dead=2/year and init_prev=0.5 '
        f'over 10 years, but cum_deaths={cum_deaths}'
    )
    n_dead_in_state = int((tb.state == TBS.DEAD).sum())
    assert n_dead_in_state == 0, (
        f'Dead agents must be ejected from tb.state; '
        f'found {n_dead_in_state} agents still in TBS.DEAD'
    )
    assert not (tb.susceptible & tb.infected).any(), (
        'No alive agent may be simultaneously susceptible and infected'
    )
    return sim


# =============================================================================
# 1.6 — dt sensitivity
# =============================================================================

@sc.timer()
def test_coarse_vs_fine_dt_agreement(do_plot=do_plot):
    """Mean prevalence from dt=7d and dt=1d must agree within 50% (1.6).

    The 50% single-seed tolerance accommodates stochastic variance at low
    prevalence. A real per-step rate-conversion bug (e.g., a weekly rate applied
    without dt normalisation) would produce a ≥5x ratio and fail reliably.
    """
    sc.heading('Testing dt sensitivity (7-day vs 1-day)...')
    kw = dict(
        n_agents=2_000,
        start=ss.date('2000-01-01'),
        stop=ss.date('2010-01-01'),
        pars=dict(init_prev=ss.bernoulli(0.20), beta=ss.peryear(0.3)),
    )
    sim_week = make_tb_sim(**kw, dt=ss.days(7))
    sim_day  = make_tb_sim(**kw, dt=ss.days(1))
    for sim in (sim_week, sim_day):
        sim.pars.rand_seed = 55
    sim_week.run(); sim_day.run()
    p_week = float(np.mean(tbsim.get_tb(sim_week).results['prevalence_active'][:]))
    p_day  = float(np.mean(tbsim.get_tb(sim_day).results['prevalence_active'][:]))
    assert np.isclose(p_week, p_day, rtol=0.50), (
        f'dt=7d prevalence ({p_week:.4f}) and dt=1d prevalence ({p_day:.4f}) '
        f'differ by more than 50%. A genuine rate-conversion bug produces '
        f'ratios of ≥5x; this discrepancy strongly indicates one.'
    )
    if do_plot:
        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        axes[0].plot(tbsim.get_tb(sim_week).results['prevalence_active'][:], label='dt=7d')
        axes[0].plot(tbsim.get_tb(sim_day).results['prevalence_active'][:],  label='dt=1d')
        axes[0].set_title('Prevalence by dt'); axes[0].legend()
        axes[1].plot(np.cumsum(tbsim.get_tb(sim_week).results['new_active'][:]), label='dt=7d')
        axes[1].plot(np.cumsum(tbsim.get_tb(sim_day).results['new_active'][:]),  label='dt=1d')
        axes[1].set_title('Cumulative new active cases'); axes[1].legend()
    return sim_week


if __name__ == '__main__':
    do_plot = True
    sc.options(interactive=do_plot)
    T = sc.timer()

    # 1.2 — invariants
    test_state_counts_sum_to_population()
    test_n_infectious_matches_infectious_states()
    test_prevalence_active_in_valid_range()
    test_cumulative_series_non_decreasing()
    test_new_events_non_negative()

    # 1.3 — rate sensitivity
    test_higher_beta_higher_prevalence(do_plot=do_plot)
    test_higher_activation_rate_more_active_earlier(do_plot=do_plot)
    test_higher_clearance_rate_lower_prevalence(do_plot=do_plot)
    test_rr_death_multiplicative(do_plot=do_plot)

    # 1.4 — initialization
    test_init_prev_respected()
    test_init_state_distribution()

    # 1.5 — death handling
    test_step_die_updates_flags_and_state()
    test_dead_agents_ejected_from_population()

    # 1.6 — dt sensitivity
    test_coarse_vs_fine_dt_agreement(do_plot=do_plot)

    T.toc()
    if do_plot:
        plt.show()
