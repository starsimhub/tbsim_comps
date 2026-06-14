# tbsim model limitations and scientific gaps

These findings are not scripted upstream bugs. They are model-scope limitations or
validation gaps that should stay visible when using this harness for scientific
scenario work.

| ID | Area | Status |
|----|------|--------|
| TGAP-001 | Prior-TB-history diagnostic stratification | open |
| TGAP-002 | Drug-resistant TB pathway and separable outputs | open |

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
