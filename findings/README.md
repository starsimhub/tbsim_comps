# tbsim findings

Upstream defects discovered by this validation harness.

| File | Purpose |
|------|---------|
| `TBSIM_KNOWN_BUGS.md` | Human-readable bug registry for filing issues with the tbsim team |
| `bug_registry.py` | Machine-readable registry (TBUG-001 … TBUG-009) |
| `issue_links.json` | Links filed `starsimhub/tbsim` GitHub issues back to failing tests |

After filing an upstream issue, link it with:

```bash
python scripts/link_tbsim_issue.py TBUG-001 425
# or
python scripts/link_tbsim_issue.py tests.test_tbsim_regressions::test_foo 425
```

The validation report also has a **Link issue** button on each failure for browser-local linking; use the script above to persist the mapping for the team.

Regression tests live in `tests/test_tbsim_regressions.py`. Run `scripts/report_tbsim_bugs.sh` for a team triage report.
