#!/usr/bin/env bash
set -euo pipefail

# Install deps from requirements.txt and run the full test harness.
#
# To test a different tbsim branch, edit the @ref in requirements.txt first:
#   tbsim @ git+https://github.com/starsimhub/tbsim.git@your-branch
#
# Usage:
#   scripts/run_tests.sh [pytest args...]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Installing dependencies from requirements.txt..."
python -m pip install --upgrade pip
python -m pip install -r "${ROOT_DIR}/requirements.txt"

python - <<'PY'
import tbsim
print("Using tbsim from:", tbsim.__file__)
PY

cd "${ROOT_DIR}"
export MPLBACKEND=Agg
export SCIRIS_BACKEND=agg

if [ "$#" -gt 0 ]; then
  python -m pytest "$@"
else
  python -m pytest tests/ -v --tb=short
fi
