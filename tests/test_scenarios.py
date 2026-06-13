"""
Scientific scenario validations for tbsim.

These tests compare intervention scenarios against matched baselines and assert
that outcomes move in epidemiologically expected directions.

Run as pytest or as a standalone script:
    python tests/test_scenarios.py
"""

import numpy as np
import sciris as sc
import starsim as ss
import matplotlib.pyplot as plt
import tbsim
from tbsim import TBS


n_agents = 1_000
do_plot = False
sc.options(interactive=False)


def get_intervention(sim, cls):
    """Return the first initialized intervention of a given class."""
    for intervention in sim.interventions.values():
        if isinstance(intervention, cls):
            return intervention
    raise AssertionError(f"Expected sim to include intervention {cls.__name__}")


def total(result):
    """Return integer total for a Starsim result array."""
    return int(np.sum(result))


def make_scenario_sim(interventions=None, seed=1, n_agents=n_agents, stop="2003", tb_pars=None):
    """Build a quiet tbsim scenario simulation."""
    sim = tbsim.Sim(
        sim_pars=dict(
            n_agents=n_agents,
            start=ss.date("2000-01-01"),
            stop=ss.date(stop),
            dt=ss.days(7),
            rand_seed=seed,
        ),
        tb_pars=tb_pars or {},
        pars=dict(interventions=interventions or []),
    )
    sim.pars.verbose = 0
    return sim


def force_latent_cohort(sim):
    """Put all agents into latent infection for prevention scenario checks."""
    sim.init()
    tb = sim.get_tb()
    uids = sim.people.auids
    tb.state[uids] = TBS.INFECTION
    tb.infected[uids] = True
    tb.susceptible[uids] = False
    tb.ever_infected[uids] = True
    return sim


@sc.timer()
def test_full_care_cascade_reduces_tb_mortality(do_plot=do_plot):
    """HSB -> Xpert -> effective treatment should reduce TB deaths vs no care."""
    baseline_deaths = []
    care_deaths = []
    care_treated = []

    for seed in [1, 2, 3]:
        tb_pars = dict(
            beta=ss.peryear(0.0),
            init_prev=ss.bernoulli(0.25),
            sym_dead=ss.peryear(1.2),
        )
        baseline = make_scenario_sim(seed=seed, n_agents=1_200, stop="2003", tb_pars=tb_pars)
        baseline.run()
        baseline_deaths.append(total(baseline.get_tb().results.new_deaths))

        interventions = [
            tbsim.HealthSeekingBehavior(pars=dict(initial_care_seeking_rate=ss.perday(1.0))),
            tbsim.DxDelivery(tbsim.Xpert(), coverage=1.0),
            tbsim.TxDelivery(tbsim.FirstLine(
                dur_treatment=ss.constant(v=14),
                efficacy=1.0,
                adherence=1.0,
                p_relapse=0.0,
            )),
        ]
        care = make_scenario_sim(
            interventions=interventions,
            seed=seed,
            n_agents=1_200,
            stop="2003",
            tb_pars=tb_pars,
        )
        care.run()
        care_deaths.append(total(care.get_tb().results.new_deaths))
        care_treated.append(total(get_intervention(care, tbsim.TxDelivery).results.n_treated))

    assert sum(care_treated) > 0, "Expected the full cascade to treat at least one diagnosed active-TB agent"
    assert sum(care_deaths) < sum(baseline_deaths), (
        f"Expected effective care cascade to reduce TB deaths; baseline={baseline_deaths}, care={care_deaths}"
    )


@sc.timer()
def test_bcg_prevention_reduces_latent_progression(do_plot=do_plot):
    """High-take BCG with strong activation protection should reduce latent progression."""
    baseline_active = []
    bcg_active = []

    for seed in [1, 2, 3]:
        tb_pars = dict(
            beta=ss.peryear(0),
            init_prev=ss.bernoulli(0),
            inf_cle=ss.peryear(0),
            inf_non=ss.peryear(0),
            inf_asy=ss.peryear(5),
        )
        baseline = make_scenario_sim(seed=seed, stop="2001", tb_pars=tb_pars)
        force_latent_cohort(baseline)
        baseline.run()
        baseline_active.append(int(np.isin(baseline.get_tb().state, TBS.active_tb_states()).sum()))

        product = tbsim.BCGVx(pars=dict(
            p_take=ss.bernoulli(p=1.0),
            dur_immune=ss.constant(v=3650),
            activation_modifier=ss.constant(v=0.1),
            clearance_modifier=ss.constant(v=1.0),
            death_modifier=ss.constant(v=1.0),
        ))
        bcg = tbsim.BCGRoutine(product=product, pars=dict(coverage=1.0, age_range=[0, 99]))
        protected = make_scenario_sim(interventions=[bcg], seed=seed, stop="2001", tb_pars=tb_pars)
        force_latent_cohort(protected)
        protected.run()
        bcg_active.append(int(np.isin(protected.get_tb().state, TBS.active_tb_states()).sum()))

    assert sum(bcg_active) < 0.6 * sum(baseline_active), (
        f"Expected BCG protection to materially reduce active progression; baseline={baseline_active}, bcg={bcg_active}"
    )


@sc.timer()
def test_tpt_sterilization_reduces_latent_progression(do_plot=do_plot):
    """High-efficacy sterilizing TPT should reduce active TB from a latent cohort."""
    baseline_active = []
    tpt_active = []

    for seed in [1, 2, 3]:
        tb_pars = dict(
            beta=ss.peryear(0),
            init_prev=ss.bernoulli(0),
            inf_cle=ss.peryear(0),
            inf_non=ss.peryear(0),
            inf_asy=ss.peryear(5),
        )
        baseline = make_scenario_sim(seed=seed, stop="2001", tb_pars=tb_pars)
        force_latent_cohort(baseline)
        baseline.run()
        baseline_active.append(int(np.isin(baseline.get_tb().state, TBS.active_tb_states()).sum()))

        product = tbsim.TPTTx(pars=dict(
            efficacy=ss.bernoulli(p=1.0),
            p_sterilize=ss.bernoulli(p=1.0),
            dur_treatment=ss.constant(v=7),
            dur_protection=ss.constant(v=365),
        ))
        tpt = tbsim.TPTSimple(product=product, pars=dict(coverage=1.0))
        prevention = make_scenario_sim(interventions=[tpt], seed=seed, stop="2001", tb_pars=tb_pars)
        force_latent_cohort(prevention)
        prevention.run()
        tpt_active.append(int(np.isin(prevention.get_tb().state, TBS.active_tb_states()).sum()))

    assert sum(tpt_active) < 0.6 * sum(baseline_active), (
        f"Expected sterilizing TPT to reduce active progression; baseline={baseline_active}, tpt={tpt_active}"
    )


@sc.timer()
def test_beta_reduction_lowers_late_incidence(do_plot=do_plot):
    """A strong beta reduction should lower late-period active TB incidence."""
    baseline_late_active = []
    reduced_late_active = []

    for seed in [1, 2, 3]:
        tb_pars = dict(beta=ss.peryear(2.0), init_prev=ss.bernoulli(0.08))
        baseline = make_scenario_sim(seed=seed, n_agents=1_500, stop="2005", tb_pars=tb_pars)
        baseline.run()
        baseline_new_active = np.array(baseline.get_tb().results.new_active)
        baseline_late_active.append(int(baseline_new_active[len(baseline_new_active) // 2:].sum()))

        reduced = make_scenario_sim(
            interventions=[tbsim.BetaByYear(pars=dict(years=[2002], x_beta=0.2))],
            seed=seed,
            n_agents=1_500,
            stop="2005",
            tb_pars=tb_pars,
        )
        reduced.run()
        reduced_new_active = np.array(reduced.get_tb().results.new_active)
        reduced_late_active.append(int(reduced_new_active[len(reduced_new_active) // 2:].sum()))

    assert sum(reduced_late_active) < sum(baseline_late_active), (
        "Expected lower beta after 2002 to lower late active TB incidence; "
        f"baseline={baseline_late_active}, reduced={reduced_late_active}"
    )


if __name__ == "__main__":
    do_plot = True
    sc.options(interactive=do_plot)
    T = sc.timer()

    test_full_care_cascade_reduces_tb_mortality(do_plot=do_plot)
    test_bcg_prevention_reduces_latent_progression(do_plot=do_plot)
    test_tpt_sterilization_reduces_latent_progression(do_plot=do_plot)
    test_beta_reduction_lowers_late_incidence(do_plot=do_plot)

    T.toc()

    if do_plot:
        plt.show()
