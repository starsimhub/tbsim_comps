#!/usr/bin/env bash
set -euo pipefail

# Report open upstream tbsim bugs for team triage.
#
# Prints the bug registry, the installed tbsim path, then runs regression tests.
# Failures are expected until upstream fixes land — use the TBUG-xxx IDs when
# opening issues on starsimhub/tbsim.
#
# Usage:
#   scripts/report_tbsim_bugs.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REGISTRY="${ROOT_DIR}/findings/TBSIM_KNOWN_BUGS.md"

echo "=== tbsim bug report ==="
echo "Harness: ${ROOT_DIR}"
echo

python - <<'PY'
import tbsim
from findings.bug_registry import OPEN_BUGS

print("Installed tbsim:", tbsim.__file__)
print()
print(f"Open bugs tracked: {len(OPEN_BUGS)}")
for bug in OPEN_BUGS:
    print(f"  {bug['id']} [{bug['severity']}] {bug['title']}")
    print(f"    test: tests/test_tbsim_regressions.py::{bug['test']}")
PY

echo
echo "=== Registry (full) ==="
sed -n '1,20p' "${REGISTRY}"
echo "..."
echo "(see findings/TBSIM_KNOWN_BUGS.md)"
echo

cd "${ROOT_DIR}"
export MPLBACKEND=Agg
export SCIRIS_BACKEND=agg

echo "=== Regression test run ==="
set +e
python -m pytest tests/test_tbsim_regressions.py -v --tb=line -m tbsim_bug 2>&1
EXIT=$?
set -e

echo
if [[ "${EXIT}" -eq 0 ]]; then
  echo "All open-bug regression tests passed — update findings/bug_registry.py if bugs were fixed upstream."
else
  echo "Regression tests failed (expected while bugs are open). File issues using TBUG-xxx IDs above."
fi

exit "${EXIT}"
