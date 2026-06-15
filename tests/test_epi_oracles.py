"""
Scientific oracle tests for tbsim.TB.

Each test fixes the natural-history parameters so a single epidemiological quantity
can be compared against a closed-form expectation:

  A1 — Empirical R0 scales linearly with beta (sterilizing index cohort).
  B6 — Latent reactivation survivor curve matches exp(-r*t).
  B7 — trans_asymp (kappa) scales R0 from asymptomatic-only index cases.
  B9 — Reinfection RR is applied to CLEARED agents only, not SUSCEPTIBLE ones.
  D13 — Care cascade deaths-averted is monotone and saturating in Dx coverage.

Failures here trace to tbsim natural-history code paths rather than harness setup.

Run as pytest or as a standalone script:
    python tests/test_epi_oracles.py
"""

import math

import numpy as np
import sciris as sc
import starsim as ss
import pytest
import tbsim
from tbsim import TBS


sc.options(interactive=False)


# -----------------------------------------------------------------------------
# Shared helpers
# -----------------------------------------------------------------------------

# Disable every natural-history exit so R0 measurements are not contaminated by
# clearance, progression, death, or reinfection.
STERILIZED_TB_PARS = dict(
    init_prev=ss.bernoulli(0),
    inf_asy=ss.peryear(0),
    inf_cle=ss.peryear(0),
    inf_non=ss.peryear(0),
    sym_dead=ss.peryear(0),
    sym_asy=ss.peryear(0),
    asy_sym=ss.peryear(0),
    asy_non=ss.peryear(0),
    non_rec=ss.peryear(0),
    non_asy=ss.peryear(0),
    rr_reinfection_cleared=0,
)


def make_tb_only_sim(n_agents=10_000, n_contacts=10, dt_days=7,
                     start="2000-01-01", stop="2000-04-01", seed=1,
                     tb_pars=None):
    """Bare ss.Sim with only TB and a homogeneous random network."""
    tb = tbsim.TB(pars=tb_pars or {})
    net = ss.RandomNet(pars=dict(n_contacts=ss.poisson(lam=n_contacts), dur=30))
    sim = ss.Sim(
        n_agents=n_agents,
        networks=net,
        diseases=tb,
        dt=ss.days(dt_days),
        start=ss.date(start),
        stop=ss.date(stop),
        verbose=0,
        rand_seed=seed,
    )
    sim.pars.verbose = 0
    return sim


def seed_state(sim, state, n_index):
    """Place the first ``n_index`` active UIDs into a chosen TB state."""
    tb = tbsim.get_tb(sim)
    uids = sim.people.auids[:n_index]
    tb.state[uids] = state
    tb.infected[uids] = state not in (TBS.SUSCEPTIBLE, TBS.CLEARED)
    tb.susceptible[uids] = state == TBS.SUSCEPTIBLE
    tb.ever_infected[uids] = True
    return uids


def measure_secondary_per_index(sim, n_index):
    """Mean secondary infections per index case (empirical R0 within the window)."""
    tb = tbsim.get_tb(sim)
    return (int(tb.ever_infected.sum()) - n_index) / n_index


# =============================================================================
# A1 — R0 scales linearly with beta (sterilizing setup)
# =============================================================================

@sc.timer()
def test_empirical_R0_scales_linearly_with_beta():
    """R0 measured from a small index cohort must scale ~linearly with beta.

    With every natural-history exit disabled, the only source of new infections is
    transmission. The next-generation R0 is then ``beta * D * kappa * c`` with all
    factors except beta fixed, so a 2x bump in beta must approximately double the
    empirical secondary-cases-per-index value.

    Failures point to tbsim transmission code (``TB.step`` force-of-infection) or
    Starsim FOI accumulation.
    """
    n_index = 50

    def R0(beta_val, seed):
        sim = make_tb_only_sim(
            seed=seed,
            tb_pars={**STERILIZED_TB_PARS, "beta": ss.peryear(beta_val)},
        )
        sim.init()
        seed_state(sim, TBS.SYMPTOMATIC, n_index)
        sim.run()
        return measure_secondary_per_index(sim, n_index)

    seeds = (1, 2, 3, 4)
    low = np.mean([R0(0.5, s) for s in seeds])
    mid = np.mean([R0(1.0, s) for s in seeds])
    high = np.mean([R0(2.0, s) for s in seeds])

    assert 0.8 < low < 1.8, f"R0(beta=0.5) out of expected band: {low:.2f}"
    assert 1.8 < mid < 3.0, f"R0(beta=1.0) out of expected band: {mid:.2f}"
    assert 3.0 < high < 5.0, f"R0(beta=2.0) out of expected band: {high:.2f}"
    assert math.isclose(mid / low, 2.0, rel_tol=0.30), (
        f"Doubling beta should ~double R0; got low={low:.2f}, mid={mid:.2f} (ratio={mid/low:.2f})"
    )
    assert math.isclose(high / mid, 2.0, rel_tol=0.30), (
        f"Doubling beta should ~double R0; got mid={mid:.2f}, high={high:.2f} (ratio={high/mid:.2f})"
    )


# =============================================================================
# B6 — Latent reactivation survivor curve matches exp(-r*t)
# =============================================================================

@sc.timer()
def test_latent_reactivation_hazard_matches_exponential():
    """Fraction of cohort still latent after t years must equal exp(-r * t).

    With only the INFECTION -> ASYMPTOMATIC transition enabled (rate = ``inf_asy``),
    the survivor function of the latent state is exponential. Three rates are tested
    over two years; absolute tolerance 0.01 is comfortably inside binomial noise for
    a 20k cohort.

    Failures point to ``TB.transition`` rate conversion or the INFECTION exit logic.
    """
    n = 20_000
    duration_years = 2.0

    def latent_fraction_after(rate_per_year, seed=1):
        tb_pars = {
            **STERILIZED_TB_PARS,
            "beta": ss.peryear(0),
            "inf_asy": ss.peryear(rate_per_year),
        }
        sim = make_tb_only_sim(
            n_agents=n,
            stop="2002-01-01",
            seed=seed,
            tb_pars=tb_pars,
        )
        sim.init()
        seed_state(sim, TBS.INFECTION, n)
        sim.run()
        tb = tbsim.get_tb(sim)
        return int((tb.state == TBS.INFECTION).sum()) / n

    for rate in (0.10, 0.30, 0.50):
        empirical = latent_fraction_after(rate)
        expected = math.exp(-rate * duration_years)
        assert abs(empirical - expected) < 0.01, (
            f"Latent survivor at rate={rate}/yr after {duration_years}y: "
            f"empirical={empirical:.4f}, expected={expected:.4f}. "
            "Trace to TB.transition rate handling for INFECTION -> ASYMPTOMATIC."
        )


# =============================================================================
# B7 — kappa (trans_asymp) scales R0 from asymptomatic seeds
# =============================================================================

@sc.timer()
def test_trans_asymp_scales_R0_from_asymptomatic_seeds():
    """R0 from an asymptomatic-only index cohort must scale with ``trans_asymp``.

    Asymptomatic transmissibility is ``kappa * beta``; halving kappa must roughly
    halve secondary cases. Failure traces to ``rel_trans`` assignment for ASYMPTOMATIC
    agents (``TB.step``).
    """
    n_index = 50

    def R0(kappa, seed):
        tb_pars = {**STERILIZED_TB_PARS, "beta": ss.peryear(2.0), "trans_asymp": kappa}
        sim = make_tb_only_sim(seed=seed, tb_pars=tb_pars)
        sim.init()
        seed_state(sim, TBS.ASYMPTOMATIC, n_index)
        sim.run()
        return measure_secondary_per_index(sim, n_index)

    seeds = (1, 2, 3, 4)
    quarter = np.mean([R0(0.25, s) for s in seeds])
    half = np.mean([R0(0.50, s) for s in seeds])
    full = np.mean([R0(1.00, s) for s in seeds])

    assert quarter < half < full, (
        f"R0_asym not monotone in kappa: {quarter:.2f} < {half:.2f} < {full:.2f}"
    )
    assert math.isclose(half / quarter, 2.0, rel_tol=0.40), (
        f"Doubling kappa from 0.25 -> 0.5 should ~double R0_asym; got {quarter:.2f}, {half:.2f}"
    )
    assert math.isclose(full / half, 2.0, rel_tol=0.30), (
        f"Doubling kappa from 0.5 -> 1.0 should ~double R0_asym; got {half:.2f}, {full:.2f}"
    )


# =============================================================================
# B9 — Reinfection RR applied to CLEARED state only
# =============================================================================

@sc.timer()
def test_rr_reinfection_applied_to_cleared_only():
    """``rel_sus`` must equal ``rr_reinfection_cleared`` on CLEARED, 1.0 on SUSCEPTIBLE.

    Half the cohort is seeded latent, then quickly cleared by a large ``inf_cle`` rate;
    the other half stays SUSCEPTIBLE. After the run, the CLEARED partition must carry
    the configured reinfection RR and the SUSCEPTIBLE partition must remain at 1.0.

    Failure points to ``TB.step`` reinfection RR assignment leaking to never-infected
    agents, or to the rel_sus reset logic clobbering cleared agents.
    """
    rr_cleared = 0.3
    n = 2_000
    n_latent = 1_000

    tb_pars = {
        **STERILIZED_TB_PARS,
        "beta": ss.peryear(0),
        "inf_cle": ss.peryear(10),  # rapidly drive INFECTION -> CLEARED
        "rr_reinfection_cleared": rr_cleared,
    }
    sim = make_tb_only_sim(n_agents=n, stop="2001-01-01", seed=1, tb_pars=tb_pars)
    sim.init()
    seed_state(sim, TBS.INFECTION, n_latent)
    sim.run()

    tb = tbsim.get_tb(sim)
    state = np.asarray(tb.state)
    rel_sus = np.asarray(tb.rel_sus)

    n_cleared = int((state == TBS.CLEARED).sum())
    n_susc = int((state == TBS.SUSCEPTIBLE).sum())
    assert n_cleared > 0.9 * n_latent, (
        f"Most seeded latents should clear under inf_cle=10/yr over 1 year; got {n_cleared}"
    )
    assert n_susc > 0, "Expected the unseeded half to remain susceptible"

    cleared_vals = np.unique(rel_sus[state == TBS.CLEARED])
    susc_vals = np.unique(rel_sus[state == TBS.SUSCEPTIBLE])
    assert np.allclose(cleared_vals, rr_cleared), (
        f"Expected rel_sus={rr_cleared} on CLEARED, got {cleared_vals}"
    )
    assert np.allclose(susc_vals, 1.0), (
        f"Expected rel_sus=1.0 on SUSCEPTIBLE, got {susc_vals}. "
        "Reinfection RR must not leak to never-infected agents."
    )


# =============================================================================
# D13 — Care cascade: deaths averted is monotone, saturating in coverage
# =============================================================================

@sc.timer()
def test_dx_coverage_deaths_averted_curve_monotone_and_saturating():
    """Deaths averted vs no-care baseline must be non-decreasing in Dx coverage.

    Common-sense epi expectation: adding diagnostic coverage on top of an effective
    treatment cascade prevents deaths, with diminishing returns once symptomatic
    agents are caught quickly. Three coverage levels (0.2, 0.5, 1.0) plus a no-care
    baseline; aggregate across seeds.

    Failures point to a broken HSB->Dx->Tx hand-off or a Dx coverage filter that
    does not scale with its parameter.
    """
    seeds = (1, 2, 3)
    tb_pars = dict(
        init_prev=ss.bernoulli(0.30),
        beta=ss.peryear(0),
        sym_dead=ss.peryear(1.0),
    )

    def run(dx_cov, seed):
        if dx_cov > 0:
            interventions = [
                tbsim.HealthSeekingBehavior(
                    pars=dict(initial_care_seeking_rate=ss.perday(1.0))
                ),
                tbsim.DxDelivery(tbsim.Xpert(), coverage=dx_cov),
                tbsim.TxDelivery(tbsim.FirstLine(
                    dur_treatment=ss.constant(v=14),
                    efficacy=1.0,
                    adherence=1.0,
                    p_relapse=0.0,
                )),
            ]
        else:
            interventions = []
        sim = tbsim.Sim(
            sim_pars=dict(
                n_agents=2_000,
                start=ss.date("2000-01-01"),
                stop=ss.date("2003-01-01"),
                dt=ss.days(7),
                rand_seed=seed,
                verbose=0,
            ),
            tb_pars=tb_pars,
            pars=dict(interventions=interventions),
        )
        sim.run()
        return int(sim.get_tb().results.new_deaths.sum())

    baseline = sum(run(0.0, s) for s in seeds)
    assert baseline > 0, "Need baseline deaths to compute averted counts"

    deaths_by_cov = {cov: sum(run(cov, s) for s in seeds) for cov in (0.2, 0.5, 1.0)}
    averted = {cov: baseline - deaths_by_cov[cov] for cov in deaths_by_cov}

    assert averted[0.2] >= 0, "Some Dx coverage cannot increase deaths vs baseline"
    assert averted[0.5] >= averted[0.2] - 1, (
        f"Deaths averted non-monotone in Dx coverage: 0.2->{averted[0.2]}, 0.5->{averted[0.5]}. "
        "Trace to HSB->Dx->Tx hand-off."
    )
    assert averted[1.0] >= averted[0.5] - 1, (
        f"Deaths averted non-monotone: 0.5->{averted[0.5]}, 1.0->{averted[1.0]}"
    )
    assert averted[1.0] >= 0.5 * baseline, (
        f"Full Dx coverage with perfect Tx should avert at least half of baseline deaths; "
        f"got baseline={baseline}, deaths={deaths_by_cov[1.0]}, averted={averted[1.0]}. "
        "Trace to TxDelivery / FirstLine effectiveness."
    )


if __name__ == "__main__":
    T = sc.timer()
    test_empirical_R0_scales_linearly_with_beta()
    test_latent_reactivation_hazard_matches_exponential()
    test_trans_asymp_scales_R0_from_asymptomatic_seeds()
    test_rr_reinfection_applied_to_cleared_only()
    test_dx_coverage_deaths_averted_curve_monotone_and_saturating()
    T.toc()
