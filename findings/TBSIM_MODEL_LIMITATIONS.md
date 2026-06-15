# tbsim model limitations and scientific gaps

These findings are not scripted upstream bugs. They are model-scope limitations or
validation gaps that should stay visible when using this harness for scientific
scenario work.

| ID | Area | Status |
|----|------|--------|
| TGAP-001 | Prior-TB-history diagnostic stratification | open |
| TGAP-002 | Drug-resistant TB pathway and separable outputs | open |
| TGAP-003 | Treatment-state guard when TxDelivery is absent | open |
| TGAP-004 | Duration-only reinfection protection is a no-op when RR is 1 | open |

## TGAP-001 — Prior-TB-history diagnostic stratification

`Xpert` probability tables currently stratify by TB state and age, but not by
prior TB, recent prior TB, or previous treatment history.

This is a scientific modeling gap rather than a package bug: the current product
does not claim prior-history-aware diagnostic behavior. Scenarios that depend on
repeated diagnosis, recent prior TB, or specificity trade-offs should state this
assumption explicitly and should not infer prior-history behavior from the
built-in `Xpert` table alone.

Relevant validation-plan item: prior-TB-history diagnostic behavior tests in
Phase 2/6.

Executable placeholder: `tests/test_tbsim_regressions.py::test_xpert_prior_tb_history_strata_are_explicit`
is marked skipped until this feature gap is intentionally implemented.

## TGAP-002 — DR-TB pathway and separable outputs

`SecondLine` treatment products are available, but `tbsim` does not currently
model a full drug-resistant TB state/pathway or separate DR/MDR treatment result
channels. `TxDelivery(SecondLine())` reports through the same generic treatment
outputs as other treatment products.

This is a model-scope limitation rather than a package bug: second-line treatment
can be simulated, but drug-resistant and drug-susceptible pathways are not
separable without additional scenario assumptions or custom reporting.

Relevant validation-plan item: drug-resistance scenario branching tests in
Phase 6/7.

Executable placeholder: `tests/test_tbsim_regressions.py::test_dr_tb_secondline_outputs_are_separable`
is marked skipped until this feature gap is intentionally implemented.

## TGAP-003 — Treatment-state guard when TxDelivery is absent

The TB natural-history step explicitly leaves `TREATMENT` outcomes to
`TxDelivery`. If a scenario or test manually puts agents in `TREATMENT` without
attaching `TxDelivery`, those agents remain in treatment indefinitely.

This is not a defect in normal model flow, because agents should only enter
`TREATMENT` through the treatment delivery pathway. It is still worth tracking as
an API guard gap: scenarios that start with pre-treated agents should either
attach `TxDelivery`, avoid the `TREATMENT` state, or receive a clear validation
error.

Executable placeholder: `tests/test_tbsim_regressions.py::test_treatment_without_tx_delivery_agents_not_stuck`
is marked skipped until this guard is intentionally implemented.

## TGAP-004 — Duration-only reinfection protection is a no-op when RR is 1

`dur_reinfection_protection` schedules a waning window, but the default
`rr_reinfection_cleared=1.0` means the scheduled protection has no effect for
agents who clear latent infection through the `INFECTION -> CLEARED` pathway.

This is not a direct model failure when parameters are explicit: a relative risk
of `1.0` means no protection. It is a configuration clarity gap because setting a
duration alone can look like it enables protection while leaving susceptibility
unchanged.

Executable placeholder: `tests/test_tbsim_regressions.py::test_reinfection_protection_skipped_when_rr_cleared_is_one`
is marked skipped until this behavior is intentionally guarded or documented.
