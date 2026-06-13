"""
Phase 2 tests for tbsim intervention products and delivery modules.

Run as pytest or as a standalone script:
    python tests/test_interventions.py
"""

import numpy as np
import sciris as sc
import starsim as ss
import matplotlib.pyplot as plt
import pytest
import tbsim
from tbsim import TBS


n_agents = 500
do_plot = False
sc.options(interactive=False)


def make_sim(interventions=None, n_agents=n_agents, stop="2002", rand_seed=1, tb_pars=None):
    """Build a tbsim.Sim with the helper APIs intervention modules expect."""
    sim = tbsim.Sim(
        sim_pars=dict(
            n_agents=n_agents,
            start=ss.date("2000-01-01"),
            stop=ss.date(stop),
            dt=ss.days(7),
            rand_seed=rand_seed,
        ),
        tb_pars=tb_pars or dict(beta=0.0, init_prev=0.0),
        pars=dict(interventions=interventions or []),
    )
    sim.pars.verbose = 0
    return sim


def get_intervention(sim, cls):
    """Return the first initialized intervention of a given class."""
    for intervention in sim.interventions.values():
        if isinstance(intervention, cls):
            return intervention
    raise AssertionError(f"Expected sim to include intervention {cls.__name__}")


def assert_probability_table_is_valid(product):
    """Check each diagnostic state/filter row has a valid probability partition."""
    df = product.df
    filter_cols = [c for c in df.columns if c not in ["state", "result", "probability"]]
    grouped = df.groupby(["state", *filter_cols], dropna=False)["probability"]
    totals = grouped.sum().to_numpy()
    probs = df["probability"].to_numpy()
    assert np.all(probs >= 0), f"Expected {product.__class__.__name__} probabilities to be non-negative"
    assert np.all(probs <= 1), f"Expected {product.__class__.__name__} probabilities to be <= 1"
    assert np.allclose(totals, 1.0, atol=1e-12), f"Expected {product.__class__.__name__} rows to sum to 1"


def get_positive_probability(product, state, **filters):
    """Look up the positive probability for one diagnostic equivalent class."""
    df = product.df
    rows = (df["state"] == state) & (df["result"] == "positive")
    for key, value in filters.items():
        if key == "age":
            rows &= (df["age_min"] <= value) & (value < df["age_max"])
        else:
            rows &= df[key] == value
    matched = df.loc[rows, "probability"].to_numpy()
    assert len(matched) == 1, f"Expected one matching probability row for {product.__class__.__name__}"
    return matched[0]


def force_active_tb(sim, uids, state=TBS.SYMPTOMATIC):
    """Set selected agents to a controlled active-TB state."""
    tb = sim.get_tb()
    tb.state[uids] = state
    tb.susceptible[uids] = False
    tb.infected[uids] = True
    tb.ever_infected[uids] = True
    return tb


@sc.timer()
def test_dx_probability_tables_are_valid(do_plot=do_plot):
    """Diagnostic product tables must define complete probability partitions."""
    for product in [tbsim.Xpert(), tbsim.OralSwab(), tbsim.FujiLAM(), tbsim.CAD()]:
        assert_probability_table_is_valid(product)


@sc.timer()
def test_dx_sensitivity_equivalent_classes(do_plot=do_plot):
    """Diagnostic tables must match the planned active-TB equivalent classes."""
    assert np.isclose(get_positive_probability(tbsim.Xpert(), TBS.SYMPTOMATIC, age=30), 0.909), \
        "Expected adult symptomatic Xpert sensitivity to be 0.909"
    assert np.isclose(get_positive_probability(tbsim.Xpert(), TBS.ASYMPTOMATIC, age=30), 0.775), \
        "Expected adult asymptomatic Xpert sensitivity to be 0.775"
    assert np.isclose(get_positive_probability(tbsim.OralSwab(), TBS.SYMPTOMATIC, age=30), 0.80), \
        "Expected adult symptomatic oral swab sensitivity to be 0.80"
    assert np.isclose(get_positive_probability(tbsim.OralSwab(), TBS.ASYMPTOMATIC, age=30), 0.30), \
        "Expected adult asymptomatic oral swab sensitivity to be 0.30"
    assert np.isclose(get_positive_probability(tbsim.FujiLAM(), TBS.SYMPTOMATIC, age=30, hiv=True), 0.75), \
        "Expected HIV-positive adult FujiLAM sensitivity to be 0.75"
    assert np.isclose(get_positive_probability(tbsim.FujiLAM(), TBS.SYMPTOMATIC, age=30, hiv=False), 0.58), \
        "Expected HIV-negative adult FujiLAM sensitivity to be 0.58"
    assert np.isclose(get_positive_probability(tbsim.CAD(), TBS.SYMPTOMATIC), 0.66), \
        "Expected CAD sensitivity to be 0.66 for symptomatic active TB"
    assert np.isclose(get_positive_probability(tbsim.CAD(), TBS.ASYMPTOMATIC), 0.66), \
        "Expected CAD sensitivity to be uniform across active TB states"


@sc.timer()
def test_dx_delivery_custom_result_state(do_plot=do_plot):
    """DxDelivery must write positives to a custom result state when requested."""
    dx = tbsim.DxDelivery(
        tbsim.CAD(),
        coverage=1.0,
        result_state="screen_positive",
        eligibility=lambda sim: sim.people.auids[:100],
    )
    sim = make_sim(interventions=[dx], n_agents=150, stop="2000-03-01", rand_seed=2)
    sim.init()
    uids = sim.people.auids[:100]
    force_active_tb(sim, uids, TBS.SYMPTOMATIC)
    sim.run()
    dx = get_intervention(sim, tbsim.DxDelivery)
    n_custom_positive = int(dx.screen_positive.sum())
    assert not hasattr(dx, "diagnosed"), "Expected custom Dx result state not to create the default diagnosed state"
    assert n_custom_positive > 0, "Expected at least one CAD-positive agent in the custom result state"


@sc.timer()
def test_dx_delivery_coverage_scales_tested_count(do_plot=do_plot):
    """Higher DxDelivery coverage should test substantially more eligible agents."""
    def run_with_coverage(coverage):
        dx = tbsim.DxDelivery(
            tbsim.CAD(),
            coverage=coverage,
            eligibility=lambda sim: sim.people.auids[:400],
        )
        sim = make_sim(interventions=[dx], n_agents=500, stop="2000-02-01", rand_seed=4)
        sim.run()
        dx = get_intervention(sim, tbsim.DxDelivery)
        return int(np.sum(dx.results.n_tested)), sim

    low, _ = run_with_coverage(0.25)
    high, sim = run_with_coverage(1.0)
    assert high > low * 2.5, f"Expected full coverage to test far more agents than 25% coverage, got {high} vs {low}"
    assert high <= 400 * sim.t.npts, "Expected tested count not to exceed eligible-per-step upper bound"


@sc.timer()
def test_health_seeking_requires_symptomatic_agents(do_plot=do_plot):
    """HSB must not create care seeking when no symptomatic agents exist."""
    hsb = tbsim.HealthSeekingBehavior(pars=dict(initial_care_seeking_rate=ss.perday(1.0)))
    sim = make_sim(interventions=[hsb], n_agents=200, stop="2000-06-01", rand_seed=3)
    sim.run()
    hsb = get_intervention(sim, tbsim.HealthSeekingBehavior)
    assert int(np.sum(hsb.results.new_sought_care)) == 0, "Expected zero care seeking without symptomatic TB"


@sc.timer()
def test_tx_product_outcome_partitions(do_plot=do_plot):
    """Treatment products must put each treated UID in success or failure, with relapse as success subset."""
    sim = make_sim(n_agents=100, stop="2000-02-01")
    sim.init()
    uids = sim.people.auids[:80]
    for product in [tbsim.DOTS(), tbsim.DOTSImproved(), tbsim.FirstLine(), tbsim.SecondLine()]:
        product.pars.p_adherence.init(sim=sim, force=True)
        product.pars.p_success.init(sim=sim, force=True)
        product.pars.p_relapse.init(sim=sim, force=True)
        outcomes = product.administer(sim, uids)
        success = outcomes["success"]
        failure = outcomes["failure"]
        relapse = outcomes["relapse"]
        assert len(success & failure) == 0, f"Expected {product.__class__.__name__} success/failure to be disjoint"
        assert len(success) + len(failure) == len(uids), f"Expected {product.__class__.__name__} to partition treated UIDs"
        assert len(relapse.remove(success)) == 0, f"Expected {product.__class__.__name__} relapse UIDs to be success subset"


@sc.timer()
def test_tx_delivery_crn_reproducibility(do_plot=do_plot):
    """TxDelivery result arrays must be reproducible with the same random seed."""
    def run_once():
        dx = tbsim.DxDelivery(
            tbsim.CAD(),
            coverage=1.0,
            eligibility=lambda sim: sim.people.auids[:120],
        )
        tx = tbsim.TxDelivery(tbsim.DOTS(dur_treatment=ss.constant(v=14), p_relapse=0.0))
        sim = make_sim(interventions=[dx, tx], n_agents=150, stop="2000-06-01", rand_seed=11)
        sim.init()
        force_active_tb(sim, sim.people.auids[:120], TBS.SYMPTOMATIC)
        sim.run()
        tx = get_intervention(sim, tbsim.TxDelivery)
        return np.array(tx.results.n_treated), np.array(tx.results.n_success), np.array(tx.results.n_failure), sim

    treated1, success1, failure1, _ = run_once()
    treated2, success2, failure2, sim = run_once()
    assert np.array_equal(treated1, treated2), "Expected n_treated to be identical under fixed seed"
    assert np.array_equal(success1, success2), "Expected n_success to be identical under fixed seed"
    assert np.array_equal(failure1, failure2), "Expected n_failure to be identical under fixed seed"


@sc.timer()
def test_bcg_rr_modifiers_written(do_plot=do_plot):
    """BCG responders must receive protective TB relative-risk modifiers."""
    product = tbsim.BCGVx(pars=dict(
        p_take=ss.bernoulli(p=1.0),
        dur_immune=ss.constant(v=365),
        activation_modifier=ss.constant(v=0.5),
        clearance_modifier=ss.constant(v=1.5),
        death_modifier=ss.constant(v=0.1),
    ))
    bcg = tbsim.BCGRoutine(product=product, pars=dict(coverage=1.0, age_range=[0, 99]))
    sim = make_sim(interventions=[bcg], n_agents=100, stop="2000-02-01", rand_seed=5)
    sim.run()
    bcg = get_intervention(sim, tbsim.BCGRoutine)
    protected = bcg.product.bcg_protected.uids
    tb = sim.get_tb()
    assert len(protected) > 0, "Expected forced-take BCG to protect eligible agents"
    bcg.product.apply_protection()
    assert np.all(tb.rr_activation[protected] < 1.0), "Expected BCG to reduce activation risk"
    assert np.all(tb.rr_clearance[protected] > 1.0), "Expected BCG to increase clearance"
    assert np.all(tb.rr_death[protected] < 1.0), "Expected BCG to reduce TB death risk"


@sc.timer()
def test_tpt_simple_targets_infection_state(do_plot=do_plot):
    """TPTSimple must protect infected latent agents without delivering to susceptible agents."""
    tpt = tbsim.TPTSimple(pars=dict(coverage=1.0))
    sim = make_sim(interventions=[tpt], n_agents=120, stop="2000-02-01", rand_seed=6)
    sim.init()
    tb = sim.get_tb()
    latent = sim.people.auids[:40]
    susceptible = sim.people.auids[40:80]
    tb.state[latent] = TBS.INFECTION
    tb.infected[latent] = True
    tb.susceptible[latent] = False
    tb.state[susceptible] = TBS.SUSCEPTIBLE
    tb.infected[susceptible] = False
    tb.susceptible[susceptible] = True
    sim.run()
    tpt = get_intervention(sim, tbsim.TPTSimple)
    assert int(np.sum(tpt.results.n_newly_initiated)) > 0, "Expected TPTSimple to initiate for latent infection"
    assert int(np.sum(tpt.product.tpt_protected[susceptible])) == 0, "Expected susceptible agents not to receive TPT protection"


@sc.timer()
def test_beta_by_year_changes_compound(do_plot=do_plot):
    """BetaByYear entries must apply once and compound multiplicatively."""
    baseline_beta = 2.0
    intervention = tbsim.BetaByYear(pars=dict(years=[2000, 2001], x_beta=[0.5, 0.8]))
    sim = make_sim(
        interventions=[intervention],
        n_agents=100,
        stop="2002",
        rand_seed=7,
        tb_pars=dict(beta=baseline_beta, init_prev=0.0),
    )
    sim.run()
    tb = sim.get_tb()
    expected_beta = baseline_beta * 0.5 * 0.8
    assert np.isclose(float(tb.pars.beta), expected_beta), f"Expected compounded beta {expected_beta}, got {tb.pars.beta}"
    beta_by_year = get_intervention(sim, tbsim.BetaByYear)
    assert beta_by_year.pars.years == [], "Expected each scheduled beta change to be consumed exactly once"


if __name__ == "__main__":
    do_plot = True
    sc.options(interactive=do_plot)
    T = sc.timer()

    test_dx_probability_tables_are_valid(do_plot=do_plot)
    test_dx_sensitivity_equivalent_classes(do_plot=do_plot)
    test_dx_delivery_custom_result_state(do_plot=do_plot)
    test_dx_delivery_coverage_scales_tested_count(do_plot=do_plot)
    test_health_seeking_requires_symptomatic_agents(do_plot=do_plot)
    test_tx_product_outcome_partitions(do_plot=do_plot)
    test_tx_delivery_crn_reproducibility(do_plot=do_plot)
    test_bcg_rr_modifiers_written(do_plot=do_plot)
    test_tpt_simple_targets_infection_state(do_plot=do_plot)
    test_beta_by_year_changes_compound(do_plot=do_plot)

    T.toc()

    if do_plot:
        plt.show()
