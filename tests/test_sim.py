"""
Integration tests for tbsim.Sim — full simulation runs with result oracles.

Uses the pip-installed tbsim package (see requirements.txt). These tests
exercise the user-facing Sim API with default demographics and networks,
then assert that the run completes and the result series are internally
consistent.
"""

import numpy as np
import sciris as sc
import starsim as ss
import pytest
import tbsim
from tbsim import TBS

sc.options(interactive=False)


def make_sim(n_agents=1_500, rand_seed=42, tb_pars=None, sim_pars=None):
    """Build a tbsim.Sim with stable defaults for integration testing."""
    default_sim_pars = dict(
        start=ss.date("2000-01-01"),
        stop=ss.date("2010-01-01"),
        dt=ss.days(7),
        rand_seed=rand_seed,
        verbose=0,
    )
    default_tb_pars = dict(
        init_prev=ss.bernoulli(0.15),
        beta=ss.peryear(0.25),
    )
    if sim_pars:
        default_sim_pars.update(sim_pars)
    if tb_pars:
        default_tb_pars.update(tb_pars)

    return tbsim.Sim(
        n_agents=n_agents,
        sim_pars=default_sim_pars,
        tb_pars=default_tb_pars,
    )


def test_tbsim_sim_runs():
    """tbsim.Sim must run end-to-end and expose a TB module with results."""
    sim = make_sim(n_agents=500)
    sim.run()
    tb = sim.get_tb()

    assert isinstance(tb, tbsim.TB)
    assert len(tb.results["timevec"]) > 0
    assert tb.results["cum_active"][-1] >= 0
    assert np.isfinite(tb.results["prevalence_active"][-1])


def test_tbsim_demo_runs():
    """tbsim.demo() must return a run Sim without plotting."""
    sim = tbsim.demo(n_agents=300, verbose=0, plot=False)
    assert isinstance(sim, tbsim.Sim)
    tb = sim.get_tb()
    assert len(tb.results["timevec"]) > 0


def test_sim_results_have_expected_series():
    """A standard run must populate the main TB outcome series."""
    sim = make_sim()
    sim.run()
    tb = sim.get_tb()

    for key in (
        "n_infectious",
        "prevalence_active",
        "incidence_kpy",
        "new_active",
        "cum_active",
        "new_deaths",
        "cum_deaths",
        "deaths_ppy",
    ):
        assert key in tb.results, f"Missing TB result key '{key}'"

    for state in TBS:
        assert f"n_{state.name}" in tb.results


def test_sim_state_counts_match_alive_population():
    """Living agents must occupy exactly one non-terminal TB state at each step."""
    sim = make_sim(n_agents=1_000)
    sim.run()
    tb = sim.get_tb()
    living_states = [s for s in TBS if s not in (TBS.DEAD, TBS.REMOVED)]

    for ti in range(len(tb.results["timevec"])):
        living_count = sum(tb.results[f"n_{state.name}"][ti] for state in living_states)
        n_alive = int(sim.results.n_alive[ti])
        assert living_count == n_alive, (
            f"Living TB states sum to {living_count} at ti={ti}, "
            f"but n_alive={n_alive}"
        )


def test_sim_invariants_over_full_run():
    """Result series must stay internally consistent at every recorded step."""
    sim = make_sim(n_agents=1_200)
    sim.run()
    tb = sim.get_tb()
    n_steps = len(tb.results["timevec"])

    for ti in range(n_steps):
        n_sym = int(tb.results["n_SYMPTOMATIC"][ti])
        n_asy = int(tb.results["n_ASYMPTOMATIC"][ti])
        n_inf = int(tb.results["n_infectious"][ti])
        assert n_inf == n_sym + n_asy, (
            f"n_infectious={n_inf} != symptomatic+asymptomatic "
            f"({n_sym}+{n_asy}) at ti={ti}"
        )

        prev = tb.results["prevalence_active"][ti]
        if np.isfinite(prev):
            assert 0 <= prev <= 1, f"prevalence_active out of range at ti={ti}: {prev}"

        assert tb.results["incidence_kpy"][ti] >= 0, f"negative incidence at ti={ti}"
        assert tb.results["new_active"][ti] >= 0, f"negative new_active at ti={ti}"
        assert tb.results["new_deaths"][ti] >= 0, f"negative new_deaths at ti={ti}"

    assert np.all(np.diff(tb.results["cum_active"][:]) >= 0), "cum_active decreased"
    assert np.all(np.diff(tb.results["cum_deaths"][:]) >= 0), "cum_deaths decreased"

    np.testing.assert_array_equal(
        np.cumsum(tb.results["new_active"][:]),
        tb.results["cum_active"][:],
        err_msg="cum_active must equal cumsum of new_active",
    )
    np.testing.assert_array_equal(
        np.cumsum(tb.results["new_deaths"][:]),
        tb.results["cum_deaths"][:],
        err_msg="cum_deaths must equal cumsum of new_deaths",
    )


def test_sim_reproducible_with_fixed_seed():
    """Two runs with the same seed must produce identical result trajectories."""
    kwargs = dict(
        n_agents=800,
        rand_seed=77,
        tb_pars=dict(init_prev=ss.bernoulli(0.20), beta=ss.peryear(0.30)),
    )
    sim_a = make_sim(**kwargs)
    sim_b = make_sim(**kwargs)
    sim_a.run()
    sim_b.run()
    tb_a = sim_a.get_tb()
    tb_b = sim_b.get_tb()

    for key in ("cum_active", "cum_deaths", "prevalence_active", "n_infectious"):
        np.testing.assert_array_equal(
            tb_a.results[key][:],
            tb_b.results[key][:],
            err_msg=f"Result '{key}' differed between reproducibility runs",
        )


def test_sim_zero_transmission_produces_no_tb_burden():
    """With init_prev=0 and beta=0, TB burden series must stay at zero."""
    sim = make_sim(
        n_agents=400,
        rand_seed=5,
        tb_pars=dict(init_prev=ss.bernoulli(0.0), beta=ss.peryear(0.0)),
    )
    sim.run()
    tb = sim.get_tb()

    assert tb.results["cum_active"][-1] == 0
    assert tb.results["cum_deaths"][-1] == 0
    assert np.all(tb.results["n_infectious"][:] == 0)
    assert np.all(tb.results["prevalence_active"][:] == 0)


def test_sim_produces_epidemic_signal_with_default_pars():
    """Default pars must generate nonzero TB activity over a 10-year run."""
    sim = make_sim(n_agents=2_000, rand_seed=11)
    sim.run()
    tb = sim.get_tb()

    assert tb.results["cum_active"][-1] > 0, "Expected some active TB cases"
    assert float(np.max(tb.results["prevalence_active"][:])) > 0, (
        "Expected positive prevalence at some point"
    )
    assert float(np.sum(tb.results["new_active"][:])) > 0, (
        "Expected nonzero new_active events"
    )


def test_sim_init_prev_respected():
    """Configured init_prev must be kept as the infected fraction right after init."""
    p, n = 0.05, 5_000
    sim = make_sim(
        n_agents=n,
        rand_seed=42,
        tb_pars=dict(init_prev=ss.bernoulli(p), beta=ss.peryear(0.25)),
    )
    sim.init()
    tb = sim.get_tb()
    n_infected = int(tb.infected.sum())
    sd = (n * p * (1 - p)) ** 0.5
    lo, hi = p * n - 3 * sd, p * n + 3 * sd
    assert lo <= n_infected <= hi, (
        f"Infected count {n_infected} outside 3-SD range "
        f"[{lo:.0f}, {hi:.0f}] for init_prev={p}, n={n}"
    )


def test_sim_prevalence_active_kept_as_n_infectious_over_n_alive():
    """prevalence_active must stay equal to n_infectious / n_alive at every step."""
    sim = make_sim(n_agents=1_500, rand_seed=19)
    sim.run()
    tb = sim.get_tb()

    for ti in range(len(tb.results["timevec"])):
        n_alive = float(sim.results.n_alive[ti])
        n_inf = float(tb.results["n_infectious"][ti])
        prev = float(tb.results["prevalence_active"][ti])
        if n_alive > 0:
            expected = n_inf / n_alive
            assert np.isclose(prev, expected, rtol=0, atol=1e-12), (
                f"prevalence_active={prev} != n_infectious/n_alive "
                f"({n_inf}/{n_alive}={expected}) at ti={ti}"
            )
        else:
            assert prev == 0, f"prevalence_active should be 0 when n_alive=0 at ti={ti}"


if __name__ == "__main__":
    pytest.main(["-x", "-v", __file__])
