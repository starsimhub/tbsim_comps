"""
dt consistency across tbsim module layers.

Starsim uses one simulation timestep (`sim.pars.dt`) for every module. These
tests run the same epidemiological scenarios at dt = 1, 7, and 30 days through
three layers:

  - TB disease only (`ss.Sim` + `tbsim.TB`)
  - Full `tbsim.Sim` (demographics, network, TB)
  - Care cascade (`HealthSeekingBehavior` -> `DxDelivery` -> `TxDelivery`)

Assertions check common-sense delivery ordering, result-array shape contracts,
and cross-dt agreement within stochastic tolerance.

Run as pytest or as a standalone script:
    python tests/test_dt_consistency.py
"""

import math

import numpy as np
import sciris as sc
import starsim as ss
import matplotlib.pyplot as plt
import pytest
import tbsim
from tbsim import TBS

n_agents = 2_000
do_plot = False
sc.options(interactive=False)

DT_DAYS = (1, 7, 30)
CASCADE_DT_DAYS = (1, 7, 30)
EPIDEMIC_SEEDS = range(1, 8)
CASCADE_SEEDS = (1, 2, 3, 4, 5)


def dt_value(days):
    """Return a Starsim duration for a calendar-day timestep."""
    return ss.days(days)


def make_tb_only_sim(n_agents=n_agents, dt_days=7, pars=None, start=None, stop=None, **kwargs):
    """Minimal ss.Sim with only TB — same pattern as tests/test_tb.py."""
    tb = tbsim.TB(pars=pars)
    net = ss.RandomNet(pars=dict(n_contacts=ss.poisson(lam=5), dur=30))
    sim = ss.Sim(
        n_agents=n_agents,
        networks=net,
        diseases=tb,
        dt=dt_value(dt_days),
        start=start or ss.date("2000-01-01"),
        stop=stop or ss.date("2010-12-31"),
        **kwargs,
    )
    sim.pars.verbose = 0
    return sim


def get_intervention(sim, cls):
    """Return the first initialized intervention of a given class."""
    for intervention in sim.interventions.values():
        if isinstance(intervention, cls):
            return intervention
    raise AssertionError(f"Expected sim to include intervention {cls.__name__}")


def total(result):
    """Return integer total for a Starsim per-step result array."""
    return int(np.sum(result))


def make_tbsim_sim(dt_days=7, seed=1, n_agents=n_agents, stop="2010", interventions=None, tb_pars=None):
    """Build a quiet full-stack tbsim.Sim at a chosen timestep."""
    sim = tbsim.Sim(
        sim_pars=dict(
            n_agents=n_agents,
            start=ss.date("2000-01-01"),
            stop=ss.date(stop),
            dt=dt_value(dt_days),
            rand_seed=seed,
            verbose=0,
        ),
        tb_pars=tb_pars or dict(
            init_prev=ss.bernoulli(0.20),
            beta=ss.peryear(0.35),
        ),
        pars=dict(interventions=interventions or []),
    )
    return sim


def make_care_cascade_sim(dt_days=7, seed=1, n_agents=3_000, stop="2005"):
    """Full care cascade with deterministic Tx for delivery-count checks."""
    tb_pars = dict(
        beta=ss.peryear(0.0),
        init_prev=ss.bernoulli(0.30),
        sym_dead=ss.peryear(1.0),
    )
    interventions = [
        tbsim.HealthSeekingBehavior(pars=dict(initial_care_seeking_rate=ss.perday(0.8))),
        tbsim.DxDelivery(tbsim.Xpert(), coverage=1.0),
        tbsim.TxDelivery(tbsim.FirstLine(
            dur_treatment=ss.constant(v=14),
            efficacy=1.0,
            adherence=1.0,
            p_relapse=0.0,
        )),
    ]
    return make_tbsim_sim(
        dt_days=dt_days,
        seed=seed,
        n_agents=n_agents,
        stop=stop,
        interventions=interventions,
        tb_pars=tb_pars,
    )


EMPIRICAL_N = 50_000
EMPIRICAL_SEED = 42


def expected_prob_per_step(rate, dt):
    """Per-step probability using Starsim dur arithmetic (canonical upstream contract)."""
    return float(rate.to_prob(dt))


def tbsim_tb_transition_prob(rate, dt):
    """Mirror ``TB.transition()`` rate conversion in ``tbsim.tb``."""
    factor = dt / rate.unit
    return 1.0 - math.exp(-rate.value * factor)


def linked_module_rate_prob(sim, rate):
    """Probability that initialized tbsim modules use via ``rate.to_prob()`` after link_rates."""
    return float(rate.to_prob())


def compound_calendar_probs(p_first, p_second):
    """Probability of at least one event over two consecutive intervals."""
    return 1.0 - (1.0 - p_first) * (1.0 - p_second)


def compound_repeated_step_prob(p_step, n_steps):
    """Probability of at least one event over *n_steps* identical hazards."""
    return 1.0 - (1.0 - p_step) ** n_steps


def binomial_tolerance(p, n=EMPIRICAL_N, sigma=4.0):
    """Four-sigma tolerance for a binomial fraction with true probability *p*."""
    p = float(np.clip(p, 1e-9, 1.0 - 1e-9))
    return sigma * math.sqrt(p * (1.0 - p) / n)


def assert_empirical_matches_expected(empirical, expected, label):
    """Assert an empirical one-step fraction matches an expected probability."""
    tol = max(binomial_tolerance(expected), 5e-4)
    assert abs(empirical - expected) <= tol, (
        f"{label}: empirical={empirical:.6f} expected={expected:.6f} "
        f"(tol={tol:.6f}). "
        f"If TB.transition diverges, inspect tbsim.tb; otherwise trace to starsim.time.Rate.to_prob."
    )


def make_rate_probe_sim(dt_days, seed=EMPIRICAL_SEED, tb_pars=None, interventions=None):
    """Initialized tbsim.Sim for one-step rate probing."""
    sim = tbsim.Sim(
        sim_pars=dict(
            n_agents=EMPIRICAL_N,
            start=ss.date("2000-01-01"),
            stop=ss.date("2001-01-01"),
            dt=dt_value(dt_days),
            rand_seed=seed,
            verbose=0,
        ),
        tb_pars=tb_pars or dict(init_prev=0, beta=0),
        pars=dict(interventions=interventions or []),
    )
    sim.init()
    return sim


def measure_tb_exit_fraction(sim, source_state, competing_rates):
    """Run exactly one ``TB.step()`` and return the fraction leaving *source_state*."""
    tb = sim.get_tb()
    uids = sim.people.auids
    tb.state[uids] = source_state
    tb.infected[uids] = True
    tb.susceptible[uids] = False
    for key, value in competing_rates.items():
        tb.pars.update({key: value})
    n_source = len(uids)
    tb.step()
    n_remaining = int((tb.state == source_state).sum())
    return (n_source - n_remaining) / n_source


def measure_tb_exit_over_steps(sim, source_state, competing_rates, n_steps):
    """Run multiple ``TB.step()`` calls at a fixed sim.dt."""
    tb = sim.get_tb()
    uids = sim.people.auids
    tb.state[uids] = source_state
    tb.infected[uids] = True
    tb.susceptible[uids] = False
    for key, value in competing_rates.items():
        tb.pars.update({key: value})
    n_source = len(uids)
    for _ in range(n_steps):
        tb.step()
    n_remaining = int((tb.state == source_state).sum())
    return (n_source - n_remaining) / n_source


def measure_hsb_seek_fraction(sim):
    """Run exactly one ``HealthSeekingBehavior.step()`` on a symptomatic cohort."""
    tb = sim.get_tb()
    tb.state[sim.people.auids] = TBS.SYMPTOMATIC
    hsb = get_intervention(sim, tbsim.HealthSeekingBehavior)
    hsb.step()
    return int(hsb.sought_care.sum()) / sim.pars.n_agents


def module_rates_from_sim(sim):
    """Return linked module rates from an initialized sim (not standalone probes)."""
    tb = sim.get_tb()
    rates = [tb.pars.inf_asy, tb.pars.sym_dead, tb.pars.asy_sym]
    for intervention in sim.interventions.values():
        for value in intervention.pars.values():
            if isinstance(value, ss.Rate):
                rates.append(value)
    return rates


def standalone_tbsim_rate_probes():
    """Unlinked rates used in tbsim pars definitions for Starsim compounding checks."""
    return [
        tbsim.TB().pars.inf_asy,
        tbsim.TB().pars.sym_dead,
        tbsim.HealthSeekingBehavior().pars.initial_care_seeking_rate,
        ss.perday(0.5),
        ss.peryear(0.30),
        ss.freqperyear(2.0),
    ]


def iter_dt_pairs():
    """All unordered dt pairs and the calendar span they cover when composed."""
    for i, d1 in enumerate(DT_DAYS):
        for d2 in DT_DAYS[i:]:
            yield d1, d2, d1 + d2


def assert_delivery_chain(tested, positive, treated):
    """Cumulative cascade counts must be ordered and nonnegative."""
    assert tested >= 0 and positive >= 0 and treated >= 0
    assert treated <= positive <= tested, (
        f"Expected tested >= positive >= treated, got tested={tested}, "
        f"positive={positive}, treated={treated}"
    )


def assert_results_match_npts(sim):
    """Public result arrays must span exactly one value per timestep."""
    npts = sim.t.npts
    tb = sim.get_tb()
    for key, arr in tb.results.items():
        if key == "timevec":
            continue
        assert len(arr) == npts, f"TB result '{key}' length {len(arr)} != npts {npts}"
    for intervention in sim.interventions.values():
        for key, arr in intervention.results.items():
            if key == "timevec":
                continue
            assert len(arr) == npts, (
                f"{intervention.name}.{key} length {len(arr)} != npts {npts}"
            )


def mean_prevalence(sim):
    """Mean active-TB prevalence over the run."""
    return float(np.mean(tbsim.get_tb(sim).results.prevalence_active[:]))


def cascade_totals(sim):
    """Return cumulative tested, positive, and treated counts."""
    dx = get_intervention(sim, tbsim.DxDelivery)
    tx = get_intervention(sim, tbsim.TxDelivery)
    return (
        total(dx.results.n_tested),
        total(dx.results.n_positive),
        total(tx.results.n_treated),
    )


# =============================================================================
# 11.3 — rate conversion contract
# =============================================================================

@sc.timer()
def test_tbsim_rate_conversion_contract_across_dt():
    """tbsim stepping must honor Starsim rate conversion at every dt and compose across dt pairs.

    Checks use real module code paths:

    - ``starsim.modules.Module.link_rates`` binds ``default_dur`` to ``sim.t.dt``
    - ``tbsim.tb.TB.transition`` converts competing exponential rates each step
    - ``tbsim.interventions.health_seeking.HealthSeekingBehavior.step`` calls
      ``rate.to_prob()`` on linked rates

    Failures in the analytic TB formula vs Starsim ``to_prob(dt)`` trace upstream to
    Starsim ``dur`` math. Failures in empirical one-step fractions trace to ``tbsim.tb``
    or ``tbsim.interventions.*``. Failures only in compounding trace to Starsim.
    """
    zero = ss.peryear(0)

    # --- A. Initialized module rates are linked to sim.dt (Starsim contract) ---
    for dt_days in DT_DAYS:
        hsb = tbsim.HealthSeekingBehavior(pars=dict(initial_care_seeking_rate=ss.perday(0.5)))
        sim = make_rate_probe_sim(dt_days, interventions=[hsb])
        dt = sim.t.dt
        for rate in module_rates_from_sim(sim):
            assert rate.default_dur == dt, (
                f"link_rates did not bind default_dur for {rate} at dt={dt_days}d; "
                "trace to starsim.modules.Module.link_rates."
            )
            assert np.isclose(
                linked_module_rate_prob(sim, rate),
                expected_prob_per_step(rate, dt),
                rtol=1e-12,
                atol=1e-15,
            ), (
                f"Linked module rate {rate} at dt={dt_days}d: "
                f"to_prob()={linked_module_rate_prob(sim, rate):.12f} != "
                f"to_prob(dt)={expected_prob_per_step(rate, dt):.12f}. "
                "Trace to starsim.time.Rate.to_prob / link_rates."
            )

    # --- B. Empirical one-step TB.transition at each dt ---
    tb_cases = [
        (
            "sym_dead from SYMPTOMATIC",
            TBS.SYMPTOMATIC,
            dict(sym_dead=ss.peryear(0.5), sym_asy=zero),
        ),
        (
            "inf_asy from INFECTION",
            TBS.INFECTION,
            dict(inf_asy=ss.peryear(0.4), inf_cle=zero, inf_non=zero),
        ),
    ]
    for label, source_state, rate_pars in tb_cases:
        active_rate = next(v for v in rate_pars.values() if v is not zero)
        for dt_days in DT_DAYS:
            sim = make_rate_probe_sim(dt_days)
            expected = expected_prob_per_step(active_rate, sim.t.dt)
            empirical = measure_tb_exit_fraction(sim, source_state, rate_pars)
            assert_empirical_matches_expected(
                empirical,
                expected,
                f"TB.transition {label} at dt={dt_days}d",
            )
            assert np.isclose(
                expected,
                tbsim_tb_transition_prob(active_rate, sim.t.dt),
                rtol=1e-12,
                atol=1e-15,
            ), (
                f"TB.transition formula diverges from Starsim for {active_rate} at dt={dt_days}d."
            )

    # --- C. Empirical one-step HSB at each dt ---
    for dt_days in DT_DAYS:
        hsb = tbsim.HealthSeekingBehavior(pars=dict(initial_care_seeking_rate=ss.perday(0.3)))
        sim = make_rate_probe_sim(dt_days, interventions=[hsb])
        rate = get_intervention(sim, tbsim.HealthSeekingBehavior).pars.initial_care_seeking_rate
        expected = linked_module_rate_prob(sim, rate)
        empirical = measure_hsb_seek_fraction(sim)
        assert_empirical_matches_expected(
            empirical,
            expected,
            f"HealthSeekingBehavior.step at dt={dt_days}d",
        )

    # --- D. dt combinations: coarse one-step vs repeated fine steps (tbsim.tb) ---
    combo_cases = [
        (7, 1, 7, ss.peryear(0.5), TBS.SYMPTOMATIC, dict(sym_dead=ss.peryear(0.5), sym_asy=zero)),
        (30, 1, 30, ss.peryear(0.5), TBS.SYMPTOMATIC, dict(sym_dead=ss.peryear(0.5), sym_asy=zero)),
        (8, 1, 8, ss.peryear(0.4), TBS.INFECTION, dict(inf_asy=ss.peryear(0.4), inf_cle=zero, inf_non=zero)),
        (37, 1, 37, ss.peryear(0.4), TBS.INFECTION, dict(inf_asy=ss.peryear(0.4), inf_cle=zero, inf_non=zero)),
    ]
    for total_days, fine_dt, fine_steps, rate, source_state, rate_pars in combo_cases:
        fine_sim = make_rate_probe_sim(fine_dt)
        coarse_sim = make_rate_probe_sim(total_days)
        fine_emp = measure_tb_exit_over_steps(fine_sim, source_state, rate_pars, fine_steps)
        coarse_emp = measure_tb_exit_fraction(coarse_sim, source_state, rate_pars)
        expected_total = expected_prob_per_step(rate, dt_value(total_days))
        tol = max(
            binomial_tolerance(expected_total),
            binomial_tolerance(fine_emp),
            binomial_tolerance(coarse_emp),
            5e-4,
        )
        assert abs(fine_emp - coarse_emp) <= tol, (
            f"Calendar composition {fine_steps}×{fine_dt}d vs 1×{total_days}d diverged for {rate}: "
            f"fine={fine_emp:.6f}, coarse={coarse_emp:.6f}, tol={tol:.6f}. "
            "Trace to tbsim.tb.TB.transition if analytic checks passed."
        )
        assert abs(coarse_emp - expected_total) <= tol, (
            f"One-step {total_days}d empirical={coarse_emp:.6f} != Starsim expected={expected_total:.6f}. "
            "Trace to starsim.time.Rate.to_prob."
        )

    # --- E. Starsim compounding across all dt pairs for initialized tbsim rates ---
    for rate in standalone_tbsim_rate_probes():
        for d1, d2, total_days in iter_dt_pairs():
            dt_total = dt_value(total_days)
            dt_1 = dt_value(d1)
            dt_2 = dt_value(d2)
            p_total = expected_prob_per_step(rate, dt_total)
            p_compound = compound_calendar_probs(
                expected_prob_per_step(rate, dt_1),
                expected_prob_per_step(rate, dt_2),
            )
            assert np.isclose(p_total, p_compound, rtol=1e-12, atol=1e-15), (
                f"Starsim compounding failed for {rate}: "
                f"p({total_days}d)={p_total:.12f} != compound(p({d1}d), p({d2}d))={p_compound:.12f}. "
                "Trace to starsim.time.Rate.to_prob."
            )

        p1 = expected_prob_per_step(rate, dt_value(1))
        p7 = expected_prob_per_step(rate, dt_value(7))
        p30 = expected_prob_per_step(rate, dt_value(30))
        p2 = expected_prob_per_step(rate, dt_value(2))
        assert np.isclose(p7, compound_repeated_step_prob(p1, 7), rtol=1e-12, atol=1e-15)
        assert np.isclose(p30, compound_repeated_step_prob(p1, 30), rtol=1e-12, atol=1e-15)
        assert np.isclose(
            p30,
            compound_calendar_probs(compound_repeated_step_prob(p7, 4), p2),
            rtol=1e-12,
            atol=1e-15,
        )


# =============================================================================
# Result container contract at each dt
# =============================================================================

@sc.timer()
def test_result_lengths_match_npts_for_each_dt():
    """TB and intervention results must have one entry per timestep."""
    for dt_days in DT_DAYS:
        sim = make_care_cascade_sim(dt_days=dt_days, seed=3)
        sim.run()
        assert_results_match_npts(sim)


# =============================================================================
# Layer 1 — TB disease only
# =============================================================================

@sc.timer()
def test_tb_only_runs_at_each_dt():
    """Bare TB sim must complete and keep prevalence in [0, 1] for every dt."""
    kw = dict(
        n_agents=n_agents,
        start=ss.date("2000-01-01"),
        stop=ss.date("2008-01-01"),
        pars=dict(init_prev=ss.bernoulli(0.25), beta=ss.peryear(0.4)),
    )
    for dt_days in DT_DAYS:
        sim = make_tb_only_sim(**kw, dt_days=dt_days)
        sim.pars.rand_seed = 11
        sim.run()
        prev = tbsim.get_tb(sim).results.prevalence_active[:]
        assert np.all((prev >= 0) & (prev <= 1)), f"prevalence out of range at dt={dt_days}d"


@sc.timer()
def test_tb_epidemic_prevalence_stable_across_dt(do_plot=do_plot):
    """Mean active prevalence from 1d and 7d timesteps should agree within 20%."""
    kw = dict(
        n_agents=n_agents,
        start=ss.date("2000-01-01"),
        stop=ss.date("2010-01-01"),
        pars=dict(init_prev=ss.bernoulli(0.30), beta=ss.peryear(0.5)),
    )
    means = {1: [], 7: [], 30: []}
    last = {}
    for seed in EPIDEMIC_SEEDS:
        for dt_days in DT_DAYS:
            sim = make_tb_only_sim(**kw, dt_days=dt_days)
            sim.pars.rand_seed = seed
            sim.run()
            means[dt_days].append(mean_prevalence(sim))
            last[dt_days] = sim

    avg = {dt_days: float(np.mean(vals)) for dt_days, vals in means.items()}
    assert np.isclose(avg[1], avg[7], rtol=0.20), (
        f"TB-only mean prevalence differs between dt=1d ({avg[1]:.5f}) and "
        f"dt=7d ({avg[7]:.5f}) by more than 20% across {len(EPIDEMIC_SEEDS)} seeds"
    )
    assert np.isclose(avg[1], avg[30], rtol=0.35), (
        f"TB-only mean prevalence differs between dt=1d ({avg[1]:.5f}) and "
        f"dt=30d ({avg[30]:.5f}) by more than 35% across {len(EPIDEMIC_SEEDS)} seeds"
    )

    if do_plot:
        fig, ax = plt.subplots(figsize=(8, 4))
        for dt_days, sim in last.items():
            ax.plot(
                tbsim.get_tb(sim).results.prevalence_active[:],
                label=f"dt={dt_days}d (seed {EPIDEMIC_SEEDS[-1]})",
            )
        ax.set_title("TB-only prevalence by dt")
        ax.legend()


# =============================================================================
# Layer 2 — full tbsim.Sim (no interventions)
# =============================================================================

@sc.timer()
def test_tbsim_sim_completes_at_each_dt():
    """Default-stack tbsim.Sim must run end-to-end at 1d, 7d, and 30d."""
    for dt_days in DT_DAYS:
        sim = make_tbsim_sim(dt_days=dt_days, seed=7)
        sim.run()
        tb = sim.get_tb()
        assert len(tb.results.prevalence_active) == sim.t.npts
        assert float(tb.results.prevalence_active[-1]) >= 0.0


# =============================================================================
# Layer 3 — care cascade delivery consistency
# =============================================================================

@sc.timer()
def test_cascade_delivery_ordering_at_each_dt():
    """Each dt must produce a nonempty, ordered HSB -> Dx -> Tx delivery chain."""
    for dt_days in CASCADE_DT_DAYS:
        sim = make_care_cascade_sim(dt_days=dt_days, seed=2)
        sim.run()
        tested, positive, treated = cascade_totals(sim)
        assert tested > 0, f"Expected Dx tests at dt={dt_days}d"
        assert positive > 0, f"Expected Dx positives at dt={dt_days}d"
        assert treated > 0, f"Expected Tx deliveries at dt={dt_days}d"
        assert_delivery_chain(tested, positive, treated)


@pytest.mark.xfail(
    reason="TBUG-005: DxDelivery default eligibility tests all alive agents without HSB",
    strict=False,
)
@sc.timer()
def test_cascade_without_hsb_zero_dx_at_each_dt():
    """DxDelivery with default eligibility must not test anyone without HSB (TBUG-005).

    Common-sense cascade contract: without health-seeking, diagnosis should not run.
    This should hold at every simulation timestep size; currently fails upstream.
    """
    for dt_days in CASCADE_DT_DAYS:
        sim = make_tbsim_sim(
            dt_days=dt_days,
            seed=4,
            n_agents=50,
            stop="2000-02-01",
            interventions=[tbsim.DxDelivery(tbsim.Xpert(), coverage=1.0)],
            tb_pars=dict(beta=ss.peryear(0.0), init_prev=ss.bernoulli(0.0)),
        )
        sim.run()
        dx = get_intervention(sim, tbsim.DxDelivery)
        assert total(dx.results.n_tested) == 0, (
            f"TBUG-005: expected zero Dx tests without HSB at dt={dt_days}d"
        )


@sc.timer()
def test_cascade_delivery_counts_consistent_across_dt():
    """Paired seeds: cumulative cascade deliveries should not diverge wildly by dt.

    Coarse timesteps skip within-step events, so tolerances are looser than for
    prevalence means. A per-step rate bug would typically produce order-of-magnitude
    gaps, not the ~30% scatter seen from discretization alone.
    """
    metrics = {dt_days: [] for dt_days in CASCADE_DT_DAYS}
    for seed in CASCADE_SEEDS:
        for dt_days in CASCADE_DT_DAYS:
            sim = make_care_cascade_sim(dt_days=dt_days, seed=seed)
            sim.run()
            metrics[dt_days].append(cascade_totals(sim))

    avg_tested = {dt_days: float(np.mean([m[0] for m in vals])) for dt_days, vals in metrics.items()}
    avg_treated = {dt_days: float(np.mean([m[2] for m in vals])) for dt_days, vals in metrics.items()}

    assert avg_tested[1] > 10 and avg_treated[1] > 10, "Fixture should yield enough deliveries to compare"
    assert np.isclose(avg_tested[1], avg_tested[7], rtol=0.45), (
        f"Mean tested differs between dt=1d ({avg_tested[1]:.1f}) and dt=7d ({avg_tested[7]:.1f})"
    )
    assert np.isclose(avg_treated[1], avg_treated[7], rtol=0.45), (
        f"Mean treated differs between dt=1d ({avg_treated[1]:.1f}) and dt=7d ({avg_treated[7]:.1f})"
    )
    assert np.isclose(avg_tested[1], avg_tested[30], rtol=0.55), (
        f"Mean tested differs between dt=1d ({avg_tested[1]:.1f}) and dt=30d ({avg_tested[30]:.1f})"
    )
    assert np.isclose(avg_treated[1], avg_treated[30], rtol=0.55), (
        f"Mean treated differs between dt=1d ({avg_treated[1]:.1f}) and dt=30d ({avg_treated[30]:.1f})"
    )


@sc.timer()
def test_care_cascade_reduces_deaths_at_each_dt():
    """Effective care must reduce TB deaths vs no-care baseline at every dt."""
    for dt_days in CASCADE_DT_DAYS:
        baseline_deaths = []
        care_deaths = []
        for seed in (1, 2, 3):
            tb_pars = dict(
                beta=ss.peryear(0.0),
                init_prev=ss.bernoulli(0.25),
                sym_dead=ss.peryear(1.2),
            )
            baseline = make_tbsim_sim(dt_days=dt_days, seed=seed, n_agents=1_500, stop="2003", tb_pars=tb_pars)
            baseline.run()
            baseline_deaths.append(total(baseline.get_tb().results.new_deaths))

            care = make_care_cascade_sim(dt_days=dt_days, seed=seed, n_agents=1_500, stop="2003")
            care.run()
            care_deaths.append(total(care.get_tb().results.new_deaths))

        assert sum(care_deaths) < sum(baseline_deaths), (
            f"Expected care cascade to reduce deaths at dt={dt_days}d; "
            f"baseline={baseline_deaths}, care={care_deaths}"
        )


@sc.timer()
def test_paired_seed_cascade_ordering_across_dt():
    """For the same seed, delivery ordering must hold at every timestep size."""
    for seed in (1, 3):
        for dt_days in CASCADE_DT_DAYS:
            sim = make_care_cascade_sim(dt_days=dt_days, seed=seed, n_agents=2_000, stop="2004")
            sim.run()
            tested, positive, treated = cascade_totals(sim)
            assert_delivery_chain(tested, positive, treated)


# =============================================================================
# Per-module dt mixing and scheduler verification
# =============================================================================

def _expected_steps(start, stop, dt_days):
    """Number of step calls a module makes given its own dt."""
    span_days = (stop.to_pandas() - start.to_pandas()).days
    return span_days // dt_days


def _mixed_dt_sim(sim_dt_days, tb_dt_days, hsb_dt_days, dx_dt_days, tx_dt_days,
                  seed=1, n_agents=2_000, stop="2002-01-01"):
    """Build a tbsim.Sim where every component has its own ``dt``."""
    tb = tbsim.TB(
        dt=dt_value(tb_dt_days),
        pars=dict(init_prev=ss.bernoulli(0.20), beta=ss.peryear(0.4),
                  sym_dead=ss.peryear(0.8)),
    )
    hsb = tbsim.HealthSeekingBehavior(
        dt=dt_value(hsb_dt_days),
        pars=dict(initial_care_seeking_rate=ss.perday(0.4)),
    )
    dx = tbsim.DxDelivery(tbsim.Xpert(), coverage=1.0, dt=dt_value(dx_dt_days))
    tx = tbsim.TxDelivery(
        tbsim.FirstLine(dur_treatment=ss.constant(v=14), efficacy=1.0,
                        adherence=1.0, p_relapse=0.0),
        dt=dt_value(tx_dt_days),
    )
    sim = tbsim.Sim(
        sim_pars=dict(
            n_agents=n_agents,
            start=ss.date("2000-01-01"),
            stop=ss.date(stop),
            dt=dt_value(sim_dt_days),
            rand_seed=seed,
            verbose=0,
        ),
        tb_model=tb,
        pars=dict(interventions=[hsb, dx, tx]),
    )
    return sim


def _component_meta(sim):
    """Return (component_name -> module) for the components under test."""
    meta = {"sim": sim, "tb": sim.get_tb()}
    for cls, key in [
        (tbsim.HealthSeekingBehavior, "hsb"),
        (tbsim.DxDelivery, "dx"),
        (tbsim.TxDelivery, "tx"),
    ]:
        meta[key] = get_intervention(sim, cls)
    return meta


# Combinations of (sim, tb, hsb, dx, tx) timesteps in days; each row mixes them.
DT_COMBINATIONS = [
    (7, 1, 30, 7, 14),
    (7, 1, 7, 7, 28),
    (1, 7, 30, 14, 30),
    (30, 1, 30, 7, 14),
    (7, 7, 7, 7, 7),  # uniform reference
]


@sc.timer()
def test_module_dt_overrides_set_independent_timelines():
    """Each tbsim component must expose its own ``t.dt`` and ``t.npts`` based on its dt."""
    for sim_dt, tb_dt, hsb_dt, dx_dt, tx_dt in DT_COMBINATIONS:
        sim = _mixed_dt_sim(sim_dt, tb_dt, hsb_dt, dx_dt, tx_dt)
        sim.init()
        components = _component_meta(sim)
        configured = {"sim": sim_dt, "tb": tb_dt, "hsb": hsb_dt, "dx": dx_dt, "tx": tx_dt}
        for name, mod in components.items():
            assert float(mod.t.dt) == configured[name], (
                f"{name} configured dt={configured[name]}d but mod.t.dt={mod.t.dt}; "
                "trace to starsim.modules.Module init_pre / Timeline setup."
            )


@sc.timer()
def test_scheduler_runs_each_module_per_its_own_dt():
    """Scheduler must advance each component's ``ti`` exactly ``npts-1`` times.

    Each module's ``ti`` is incremented by Starsim's scheduler after every step
    invocation. After ``sim.run()`` we therefore expect ``mod.ti == mod.t.npts - 1``
    for every component, regardless of whether the component shares ``sim.dt`` or
    has its own ``dt``. Common-sense expectation: a component with ``dt=1d`` advances
    about 7x more often than a sibling with ``dt=7d`` over the same calendar window.

    Failures trace to ``starsim.sim.Sim.run`` scheduling rather than tbsim.
    """
    for sim_dt, tb_dt, hsb_dt, dx_dt, tx_dt in DT_COMBINATIONS:
        sim = _mixed_dt_sim(sim_dt, tb_dt, hsb_dt, dx_dt, tx_dt)
        sim.run()
        components = _component_meta(sim)
        configured = {"sim": sim_dt, "tb": tb_dt, "hsb": hsb_dt, "dx": dx_dt, "tx": tx_dt}

        for name, mod in components.items():
            expected = mod.t.npts - 1
            assert mod.ti == expected, (
                f"{name}.ti={mod.ti} != npts-1={expected} at dt={configured[name]}d "
                f"(sim_dt={sim_dt}d). Trace to starsim.sim.Sim.run scheduling."
            )
            # Each step writes one result row; sizing confirms the scheduler fired
            # update_results for every internal step.
            if name == "sim":
                continue
            for key, arr in mod.results.items():
                if key == "timevec":
                    continue
                assert len(arr) == mod.t.npts, (
                    f"{name}.{key} length {len(arr)} != npts {mod.t.npts}"
                )

        # Common-sense ratio: finer dt → more steps over the same calendar window.
        ti_by_name = {n: m.ti for n, m in components.items()}
        for name in ("tb", "hsb", "dx", "tx"):
            ratio = ti_by_name[name] / max(ti_by_name["dx"], 1)
            expected_ratio = configured["dx"] / configured[name]
            assert math.isclose(ratio, expected_ratio, rel_tol=0.05, abs_tol=0.1), (
                f"Step-count ratio {name}/dx = {ratio:.3f} differs from dt ratio "
                f"{expected_ratio:.3f} at combo (sim={sim_dt}, tb={tb_dt}, hsb={hsb_dt}, "
                f"dx={dx_dt}, tx={tx_dt})."
            )


@sc.timer()
def test_mixed_dt_results_align_with_component_timelines():
    """Each component's result arrays must align with its own ``t.npts`` and time window."""
    for sim_dt, tb_dt, hsb_dt, dx_dt, tx_dt in DT_COMBINATIONS:
        sim = _mixed_dt_sim(sim_dt, tb_dt, hsb_dt, dx_dt, tx_dt)
        sim.run()
        components = _component_meta(sim)

        for name, mod in components.items():
            if name == "sim":
                continue
            for key, arr in mod.results.items():
                if key == "timevec":
                    continue
                assert len(arr) == mod.t.npts, (
                    f"{name}.{key} length {len(arr)} != {name}.t.npts {mod.t.npts}; "
                    "trace to module init_results sizing."
                )
            tv = mod.results.timevec
            assert len(tv) == mod.t.npts, f"{name}.timevec length mismatch"
            assert tv[0] == sim.t.start, (
                f"{name}.timevec start {tv[0]} != sim.start {sim.t.start}"
            )


@sc.timer()
def test_mixed_dt_cascade_delivers_events():
    """End-to-end care cascade must still produce deliveries when components mix dt."""
    seeds = (1, 2, 3)
    for sim_dt, tb_dt, hsb_dt, dx_dt, tx_dt in DT_COMBINATIONS:
        tested_total = positive_total = treated_total = 0
        for seed in seeds:
            sim = _mixed_dt_sim(sim_dt, tb_dt, hsb_dt, dx_dt, tx_dt, seed=seed, stop="2003-01-01")
            sim.run()
            tested, positive, treated = cascade_totals(sim)
            assert_delivery_chain(tested, positive, treated)
            tested_total += tested
            positive_total += positive
            treated_total += treated
        assert tested_total > 0 and treated_total > 0, (
            f"Mixed-dt combo (sim={sim_dt}, tb={tb_dt}, hsb={hsb_dt}, dx={dx_dt}, tx={tx_dt}) "
            f"produced no deliveries across {len(seeds)} seeds; "
            "trace to per-module scheduling or eligibility filters."
        )


if __name__ == "__main__":
    do_plot = True
    sc.options(interactive=do_plot)
    T = sc.timer()

    test_tbsim_rate_conversion_contract_across_dt()
    test_result_lengths_match_npts_for_each_dt()
    test_tb_only_runs_at_each_dt()
    test_tb_epidemic_prevalence_stable_across_dt(do_plot=do_plot)
    test_tbsim_sim_completes_at_each_dt()
    test_cascade_delivery_ordering_at_each_dt()
    test_cascade_without_hsb_zero_dx_at_each_dt()
    test_cascade_delivery_counts_consistent_across_dt()
    test_care_cascade_reduces_deaths_at_each_dt()
    test_paired_seed_cascade_ordering_across_dt()
    test_module_dt_overrides_set_independent_timelines()
    test_scheduler_runs_each_module_per_its_own_dt()
    test_mixed_dt_results_align_with_component_timelines()
    test_mixed_dt_cascade_delivers_events()

    T.toc()
    if do_plot:
        plt.show()
