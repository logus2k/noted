#!/bin/bash
# Run noted integration tests against a live Docker Compose stack.
#
# Usage:
#   ./tests/run-tests.sh              # Run all tests
#   ./tests/run-tests.sh -k "test_01" # Run specific test file
#   ./tests/run-tests.sh --api-only   # Skip Playwright E2E tests
#
# Jenkins pipeline step:
#   sh './tests/run-tests.sh'
#   junit 'tests/results/results.xml'
#
# Prerequisites:
#   The noted stack must be running:
#   cd services && docker compose -f docker-compose.yml -f ../data/docker-compose.mounts.yml up -d

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
mkdir -p "${RESULTS_DIR}"

# Parse args
EXTRA_ARGS=""
API_ONLY=false
for arg in "$@"; do
    if [ "$arg" = "--api-only" ]; then
        API_ONLY=true
    else
        EXTRA_ARGS="${EXTRA_ARGS} ${arg}"
    fi
done

if [ "$API_ONLY" = true ]; then
    EXTRA_ARGS="${EXTRA_ARGS} -m api"
fi

# Build and run the test container
cd "${SCRIPT_DIR}"
docker compose -f docker-compose.test.yml build noted-test
docker compose -f docker-compose.test.yml run --rm noted-test \
    -v --tb=short -x \
    --junitxml=/tests/results/results.xml \
    ${EXTRA_ARGS}

EXIT_CODE=$?

echo ""
echo "Results: ${RESULTS_DIR}/results.xml"
exit ${EXIT_CODE}
