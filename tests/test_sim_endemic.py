"""
Endemic TB with treatment and TPT — steady-state and golden-trajectory tests.

Closed large population (no births, zero background deaths), ongoing transmission,
and a moderate Dx/Tx/TPT cascade. Agents are cleared by treatment and TPT, but
reinfection keeps active prevalence from collapsing to zero.
"""

from pathlib import Path

import numpy as np
import sciris as sc
import starsim as ss
import pytest
import tbsim

sc.options(interactive=False)

DATA_DIR = Path(__file__).parent / "data"
GOLDEN_PATH = DATA_DIR / "tb_endemic_care_golden.csv"

# Fixed scenario constants — do not change without regenerating the golden file.
N_AGENTS = 15_000
RAND_SEED = 2024
BETA = 3.0
INIT_PREV = 0.30
STEADY_STATE_START_TI = 1_040  # ~year 20
STEPS_PER_YEAR = 52


def make_endemic_care_sim():
    """
    Large closed-population sim with health seeking, Dx/Tx, and TPT.

    Demographics use ``Deaths(death_rate=0)`` so tbsim.Sim does not inject
    ``Births()`` while keeping the population size fixed.
    """
    hsb = tbsim.HealthSeekingBehavior(
        pars=dict(initial_care_seeking_rate=ss.perday(0.03)),
    )
    screen = tbsim.DxDelivery(
        name="screen",
        product=tbsim.CAD(),
        coverage=0.3,
        result_state="screen_positive",
        result_validity=ss.days(180),
    )
    confirm = tbsim.DxDelivery(
        name="confirm",
        product=tbsim.Xpert(),
        coverage=0.45,
        eligibility=lambda sim: (
            sim.people.screen.screen_positive & ~sim.people.confirm.tested
        ).uids,
        result_state="diagnosed",
        result_validity=ss.days(365),
    )
    treat = tbsim.TxDelivery(product=tbsim.DOTS())
    tpt = tbsim.TPTSimple(
        product=tbsim.TPTTx(
            pars=dict(
                efficacy=ss.bernoulli(0.35),
                p_sterilize=ss.bernoulli(0.0),
            )
        ),
        pars=dict(coverage=0.2, start=ss.date("2005-01-01")),
    )

    return tbsim.Sim(
        n_agents=N_AGENTS,
        demographics=[ss.Deaths(pars=dict(death_rate=ss.peryear(0)))],
        networks=[ss.RandomNet(pars=dict(n_contacts=ss.poisson(lam=8), dur=0))],
        sim_pars=dict(
            start=ss.date("2000-01-01"),
            stop=ss.date("2050-01-01"),
            dt=ss.days(7),
            rand_seed=RAND_SEED,
            verbose=0,
        ),
        tb_pars=dict(
            init_prev=ss.bernoulli(INIT_PREV),
            beta=ss.peryear(BETA),
        ),
        interventions=[hsb, screen, confirm, treat, tpt],
    )


def _load_golden_yearly():
    """Load yearly checkpoint columns from the committed golden CSV."""
    data = np.genfromtxt(
        GOLDEN_PATH,
        delimiter=",",
        names=True,
        dtype=None,
        encoding=None,
    )
    return {
        "year": np.asarray(data["year"], dtype=int),
        "ti": np.asarray(data["ti"], dtype=int),
        "prevalence_active": np.asarray(data["prevalence_active"], dtype=float),
        "n_infectious": np.asarray(data["n_infectious"], dtype=float),
        "n_cleared": np.asarray(data["n_cleared"], dtype=float),
    }


def test_endemic_care_clears_then_reinfects_maintains_prevalence():
    """
    Treatment and TPT must clear cases, reinfection must follow, and endemic
    active prevalence must persist in the late run (TB is not eliminated).
    """
    sim = make_endemic_care_sim()
    sim.run()
    tb = sim.get_tb()

    prev = np.asarray(tb.results["prevalence_active"][:], dtype=float)
    cleared = np.asarray(tb.results["n_CLEARED"][:], dtype=float)
    new_active = np.asarray(tb.results["new_active"][:], dtype=int)
    late_prev = prev[STEADY_STATE_START_TI:]

    cum_success = int(sim.results.txdelivery.cum_success[-1])
    peak_ti = int(np.argmax(cleared))
    post_peak_new_active = int(new_active[peak_ti:].sum())

    assert cum_success > 500, (
        f"Expected substantial treatment success, got cum_success={cum_success}"
    )
    assert float(cleared.max()) > 5_000, (
        f"Expected large cleared pool from Tx/TPT, got peak n_CLEARED={cleared.max()}"
    )
    assert post_peak_new_active > 1_000, (
        "Expected reinfection (new_active) after the clearance peak; "
        f"got post_peak_new_active={post_peak_new_active}"
    )
    assert float(late_prev.mean()) > 0.003, (
        f"Late-window mean prevalence too low for endemic steady state: "
        f"{late_prev.mean():.6f}"
    )
    assert float(prev[-1]) > 0.003, (
        f"Final active prevalence should remain endemic, got {prev[-1]:.6f}"
    )
    assert not np.all(late_prev == 0), (
        "Active prevalence must not be permanently zero in the steady-state window"
    )
    assert int(sim.results.n_alive[-1]) >= int(0.9 * N_AGENTS), (
        "Without births the population may shrink only from TB mortality; "
        f"got n_alive={int(sim.results.n_alive[-1])} for n_agents={N_AGENTS}"
    )


def test_endemic_care_prevalence_golden_trajectory():
    """Yearly prevalence checkpoints must match the committed golden trajectory."""
    assert GOLDEN_PATH.is_file(), f"Missing golden file: {GOLDEN_PATH}"

    golden = _load_golden_yearly()
    sim = make_endemic_care_sim()
    sim.run()
    tb = sim.get_tb()

    prev = np.asarray(tb.results["prevalence_active"][:], dtype=float)
    n_inf = np.asarray(tb.results["n_infectious"][:], dtype=float)
    cleared = np.asarray(tb.results["n_CLEARED"][:], dtype=float)

    tis = golden["ti"]
    actual_prev = prev[tis]
    actual_inf = n_inf[tis]
    actual_cleared = cleared[tis]

    np.testing.assert_allclose(
        actual_prev,
        golden["prevalence_active"],
        rtol=1e-4,
        atol=1e-6,
        err_msg="prevalence_active yearly checkpoints differ from golden trajectory",
    )
    np.testing.assert_allclose(
        actual_inf,
        golden["n_infectious"],
        rtol=0,
        atol=0.5,
        err_msg="n_infectious yearly checkpoints differ from golden trajectory",
    )
    np.testing.assert_allclose(
        actual_cleared,
        golden["n_cleared"],
        rtol=1e-4,
        atol=1.0,
        err_msg="n_CLEARED yearly checkpoints differ from golden trajectory",
    )


if __name__ == "__main__":
    pytest.main(["-x", "-v", __file__])
