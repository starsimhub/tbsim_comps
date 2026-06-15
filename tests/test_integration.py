"""
Phase 6 integration tests for tbsim cascade chains.

Each test runs a full tbsim.Sim with a defined cascade and checks end-to-end
results. Coverage:

  6.1 Standard care cascade
      - cascade_coverage_ordering: 80%/80%/80% delivers ~51% of cases
      - cascaded_dx_second_product: screen -> confirm two-stage diagnosis

  6.2 TPT cascade
      - tpt_household_cascade: TxDelivery -> HouseholdContactTracing -> TPT

Tests not duplicated here (already covered):
  - full_cascade_hsb_dx_tx       -> tests/test_scenarios.py
  - cascade_without_hsb          -> tests/test_dt_consistency.py (xfail TBUG-005)
  - tpt_prevents_progression     -> tests/test_scenarios.py
  - ode_vs_ss_agreement          -> TB_ODE / TB_SS not present in current tbsim
"""

import numpy as np
import sciris as sc
import starsim as ss
import pytest
import tbsim
from tbsim import TBS


n_agents = 1_500
sc.options(interactive=False)


def synthetic_dhs_data(n_households=300, seed=12345):
    """Build a minimal DHS-style household table for ``ss.HouseholdNet``."""
    rng = np.random.default_rng(seed)
    ages_per_hh = []
    for _ in range(n_households):
        size = int(rng.integers(2, 6))
        ages = rng.integers(0, 80, size=size)
        ages_per_hh.append(", ".join(str(a) for a in ages))
    return sc.dataframe(hh_id=np.arange(n_households), ages=ages_per_hh)


def household_network():
    """Static household network suitable for HouseholdContactTracing in tests."""
    return ss.HouseholdNet(dhs_data=synthetic_dhs_data(), dynamic=False)


def get_intervention(sim, cls, name=None):
    """Return the first matching initialized intervention."""
    for intervention in sim.interventions.values():
        if isinstance(intervention, cls) and (name is None or intervention.name == name):
            return intervention
    raise AssertionError(f"Expected intervention {cls.__name__} ({name=}) in sim")


def total(result):
    """Sum a per-step result array as int."""
    return int(np.sum(result))


def make_cascade_sim(interventions, seed=1, n_agents=n_agents, stop="2003-01-01",
                     tb_pars=None, networks=None, n_contacts=5):
    """Build a tbsim.Sim with a care-cascade configuration."""
    nets = networks if networks is not None else [
        ss.RandomNet(pars=dict(n_contacts=ss.poisson(lam=n_contacts), dur=30)),
    ]
    sim = tbsim.Sim(
        sim_pars=dict(
            n_agents=n_agents,
            start=ss.date("2000-01-01"),
            stop=ss.date(stop),
            dt=ss.days(7),
            rand_seed=seed,
            verbose=0,
        ),
        tb_pars=tb_pars or dict(
            init_prev=ss.bernoulli(0.30),
            beta=ss.peryear(0.0),
            sym_dead=ss.peryear(0.2),
        ),
        networks=nets,
        pars=dict(interventions=interventions),
    )
    return sim


# =============================================================================
# 6.1 Standard care cascade
# =============================================================================

@sc.timer()
def test_cascade_dx_coverage_monotonic_in_short_window():
    """Higher DxDelivery coverage must produce strictly more treatments in a short window.

    Metamorphic relation: Dx coverage gates the cascade between HSB and Tx. Over a
    short window (1 month) coverage does not have time to saturate via per-step
    retries, so ordering by Dx coverage must transfer to ordering at the Tx output.

    Failure points to DxDelivery ignoring its coverage filter, or downstream Tx
    consuming agents that should have been gated out.
    """
    def run_cascade(seed, dx_cov):
        hsb = tbsim.HealthSeekingBehavior(
            pars=dict(initial_care_seeking_rate=ss.perday(1.0)),
        )
        dx = tbsim.DxDelivery(tbsim.Xpert(), coverage=dx_cov)
        tx = tbsim.TxDelivery(
            tbsim.FirstLine(
                dur_treatment=ss.constant(v=14),
                efficacy=1.0,
                adherence=1.0,
                p_relapse=0.0,
            ),
        )
        sim = make_cascade_sim(
            interventions=[hsb, dx, tx],
            seed=seed,
            n_agents=4_000,
            stop="2000-02-01",
            tb_pars=dict(
                init_prev=ss.bernoulli(0.50),
                beta=ss.peryear(0.0),
                sym_dead=ss.peryear(0.0),
            ),
        )
        sim.run()
        return total(get_intervention(sim, tbsim.TxDelivery).results.n_treated)

    seeds = (1, 2, 3, 4, 5)
    low = [run_cascade(s, dx_cov=0.20) for s in seeds]
    mid = [run_cascade(s, dx_cov=0.50) for s in seeds]
    high = [run_cascade(s, dx_cov=1.00) for s in seeds]

    assert sum(high) > 0, "Full-coverage cascade must produce treatments"
    assert sum(low) < sum(mid) < sum(high), (
        f"Cascade coverage ordering violated: low={sum(low)}, mid={sum(mid)}, "
        f"high={sum(high)} (per seed: low={low}, mid={mid}, high={high}). "
        "Trace to DxDelivery coverage filter."
    )
    assert sum(mid) > 1.5 * sum(low), (
        f"Expected meaningful gap between 20% and 50% Dx coverage; "
        f"got low={sum(low)} mid={sum(mid)}."
    )


@sc.timer()
def test_cascaded_dx_second_product():
    """Two DxDelivery stages must chain: a confirm Dx only tests screen-positives.

    Stage 1 writes a custom result state; stage 2's eligibility filter consumes
    that state. If the chain is broken (eligibility ignored, result state never
    set), stage 2 will either test everyone (TBUG-005-like) or no one.
    """
    hsb = tbsim.HealthSeekingBehavior(
        pars=dict(initial_care_seeking_rate=ss.perday(0.6)),
    )
    screen = tbsim.DxDelivery(
        tbsim.CAD(),
        coverage=1.0,
        name="screen",
        result_state="screen_pos",
    )
    confirm = tbsim.DxDelivery(
        tbsim.Xpert(),
        coverage=1.0,
        name="confirm",
        eligibility=lambda sim: (
            sim.people.screen.screen_pos & ~sim.people.confirm.tested
        ).uids,
    )
    sim = make_cascade_sim(
        interventions=[hsb, screen, confirm],
        seed=11,
        n_agents=2_000,
        stop="2002-01-01",
    )
    sim.run()

    screen_tested = total(get_intervention(sim, tbsim.DxDelivery, "screen").results.n_tested)
    screen_pos = total(get_intervention(sim, tbsim.DxDelivery, "screen").results.n_positive)
    confirm_tested = total(get_intervention(sim, tbsim.DxDelivery, "confirm").results.n_tested)
    confirm_pos = total(get_intervention(sim, tbsim.DxDelivery, "confirm").results.n_positive)

    assert screen_tested > 0, "Stage 1 (screen) must run at least one test"
    assert screen_pos > 0, "Stage 1 must produce at least one positive to feed stage 2"
    assert 0 < confirm_tested <= screen_pos + 5, (
        f"Stage 2 should only test screen-positives ({screen_pos}); "
        f"got confirm_tested={confirm_tested}. "
        "Trace to DxDelivery eligibility chaining or screen result_state."
    )
    assert confirm_pos > 0, "Stage 2 should produce at least one Xpert positive"


# =============================================================================
# 6.2 TPT cascade
# =============================================================================

@sc.timer()
def test_tpt_household_cascade_identifies_contacts():
    """TxDelivery -> HouseholdContactTracing must flag household members.

    Without a household network, contact tracing has no edges to follow and
    should produce zero contacts. With a household network, treatment starts
    must propagate to household contacts.

    Failure traces to:
      - HouseholdContactTracing.find_household_net (no household network)
      - TxDelivery not setting on_treatment in time for tracing
      - household_ids mapping (issue #425 family)
    """
    hh_net = household_network()
    hsb = tbsim.HealthSeekingBehavior(
        pars=dict(initial_care_seeking_rate=ss.perday(0.8)),
    )
    dx = tbsim.DxDelivery(tbsim.Xpert(), coverage=1.0)
    tx = tbsim.TxDelivery(
        tbsim.FirstLine(
            dur_treatment=ss.constant(v=14),
            efficacy=1.0,
            adherence=1.0,
            p_relapse=0.0,
        ),
    )
    tracing = tbsim.HouseholdContactTracing(coverage=1.0, disease="tb")

    sim = make_cascade_sim(
        interventions=[hsb, dx, tx, tracing],
        seed=7,
        n_agents=2_000,
        stop="2002-01-01",
        networks=[hh_net],
    )
    sim.run()

    treated = total(get_intervention(sim, tbsim.TxDelivery).results.n_treated)
    tracer = get_intervention(sim, tbsim.HouseholdContactTracing)

    assert treated > 0, "Need treatment starts to seed contact tracing"

    n_contacts = total(tracer.results.n_contacts_identified)
    n_followed = total(tracer.results.n_index_followed_up)
    assert n_followed > 0, (
        f"HouseholdContactTracing must follow up at least one index case when "
        f"{treated} treatments occur."
    )
    assert n_contacts > 0, (
        f"HouseholdContactTracing must identify at least one household contact when "
        f"{n_followed} index cases are followed up. "
        "Trace to HouseholdContactTracing.step / household_ids."
    )


@sc.timer()
def test_tpt_household_full_cascade_initiates_tpt():
    """TxDelivery -> HouseholdContactTracing -> TPTHousehold must initiate TPT.

    Smoke-tests the full TPT household cascade end-to-end.
    """
    hh_net = household_network()
    hsb = tbsim.HealthSeekingBehavior(
        pars=dict(initial_care_seeking_rate=ss.perday(0.8)),
    )
    dx = tbsim.DxDelivery(tbsim.Xpert(), coverage=1.0)
    tx = tbsim.TxDelivery(
        tbsim.FirstLine(
            dur_treatment=ss.constant(v=14),
            efficacy=1.0,
            adherence=1.0,
            p_relapse=0.0,
        ),
    )
    tpt = tbsim.TPTHousehold(
        product=tbsim.TPTTx(pars=dict(
            efficacy=ss.bernoulli(0.7),
            p_sterilize=ss.bernoulli(0.0),
        )),
        pars=dict(coverage=1.0),
    )

    sim = make_cascade_sim(
        interventions=[hsb, dx, tx, tpt],
        seed=21,
        n_agents=2_000,
        stop="2002-01-01",
        networks=[hh_net],
    )
    sim.run()

    treated = total(get_intervention(sim, tbsim.TxDelivery).results.n_treated)
    assert treated > 0, "Need treatment starts to seed TPT household delivery"

    tpt_intv = get_intervention(sim, tbsim.TPTHousehold)
    initiated = 0
    for key, arr in tpt_intv.results.items():
        if "newly" in key.lower() or "initiated" in key.lower():
            initiated += total(arr)
    assert initiated > 0, (
        f"TPTHousehold must initiate prophylaxis when TxDelivery treats {treated} "
        "index cases; trace to TPTHousehold.step / eligibility filter."
    )


if __name__ == "__main__":
    T = sc.timer()
    test_cascade_dx_coverage_monotonic_in_short_window()
    test_cascaded_dx_second_product()
    test_tpt_household_cascade_identifies_contacts()
    test_tpt_household_full_cascade_initiates_tpt()
    T.toc()
