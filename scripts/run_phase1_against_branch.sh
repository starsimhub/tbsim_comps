#!/usr/bin/env bash
set -euo pipefail

# Run Phase 1 tests against a specific tbsim branch/tag/SHA.
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
WORK_DIR="${ROOT_DIR}/.tmp/tbsim-src"

echo "Preparing branch test run..."
echo "  Repo:   ${REPO}"
echo "  Ref:    ${BRANCH}"
echo "  Root:   ${ROOT_DIR}"
echo "  Source: ${WORK_DIR}"

rm -rf "${WORK_DIR}"
mkdir -p "$(dirname "${WORK_DIR}")"

git clone --depth 1 --branch "${BRANCH}" "https://github.com/${REPO}.git" "${WORK_DIR}"

python -m pip install --upgrade pip
python -m pip install -e "${WORK_DIR}"
python -m pip install pytest pytest-env pytest-xdist

TMP_RUN_DIR="$(mktemp -d)"
cd "${TMP_RUN_DIR}"

python - <<'PY'
import tbsim
print("Using tbsim from:", tbsim.__file__)
PY

MPLBACKEND=Agg SCIRIS_BACKEND=agg python -m pytest "${ROOT_DIR}/tests/test_tb.py" -v --tb=short
