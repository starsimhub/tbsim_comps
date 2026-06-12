#!/usr/bin/env bash
set -euo pipefail

# Install tbsim from a specific branch/tag/SHA and run the test suite.
#
# Usage:
#   scripts/run_phase1_against_branch.sh [branch-or-sha] [owner/repo]
#
# Examples:
#   scripts/run_phase1_against_branch.sh main
#   scripts/run_phase1_against_branch.sh fix-uid starsimhub/tbsim
#   scripts/run_phase1_against_branch.sh my-branch yourname/tbsim

BRANCH="${1:-main}"
REPO="${2:-starsimhub/tbsim}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Preparing branch test run..."
echo "  Repo: ${REPO}"
echo "  Ref:  ${BRANCH}"
echo "  Root: ${ROOT_DIR}"

python -m pip install --upgrade pip
python -m pip install "tbsim @ git+https://github.com/${REPO}.git@${BRANCH}"
python -m pip install pytest pytest-env pytest-xdist

python - <<'PY'
import tbsim
print("Using tbsim from:", tbsim.__file__)
PY

cd "${ROOT_DIR}"
export MPLBACKEND=Agg
export SCIRIS_BACKEND=agg
python -m pytest tests/ -v --tb=short
