#!/bin/bash
# Run all test suites for noted.
# Must be run from the HOST (not inside a container) since it restarts noted.
#
# Usage:
#   cd tests && ./run-all.sh
#   cd tests && ./run-all.sh --timeout=120   # pass extra pytest args
#
set -e

NETWORK="noted-network"
NOTED_URL="http://noted:8123"
PROJECT="noted-testing"
TERMINAL_SECRET="${NOTED_TERMINAL_SECRET:-2cool4u123!}"
DOCKER_IMAGE="noted-test"

# Build test image
echo "=== Building test image ==="
docker build -t "$DOCKER_IMAGE" .

# Ensure noted is responsive
wait_for_noted() {
    echo "  Waiting for noted to become responsive..."
    for i in $(seq 1 40); do
        if docker run --rm --network "$NETWORK" --entrypoint curl "$DOCKER_IMAGE" \
            -sf "$NOTED_URL/api/files/" -o /dev/null 2>/dev/null; then
            echo "  Noted responsive after $((i * 3))s"
            return 0
        fi
        sleep 3
    done
    echo "  ERROR: noted not responsive after 120s"
    return 1
}

echo ""
echo "=== Phase 1: Kernel (Socket.IO) tests ==="
echo "  Creates MLflow runs, experiments, and metrics for Phase 2"
wait_for_noted
docker run --rm --network "$NETWORK" \
    -e NOTED_URL="$NOTED_URL" \
    -e NOTED_PROJECT="$PROJECT" \
    -e NOTED_TERMINAL_SECRET="$TERMINAL_SECRET" \
    --entrypoint bash "$DOCKER_IMAGE" \
    -c "cd /tests/kernel_tests && pytest -v --tb=short --junitxml=/tests/results/kernel.xml $*"

echo ""
echo "=== Restarting noted (kernel teardown leaves server unstable) ==="
docker restart noted
sleep 10

echo ""
echo "=== Phase 2: API + E2E tests ==="
echo "  Uses MLflow data created by Phase 1"
wait_for_noted
docker run --rm --network "$NETWORK" \
    -e NOTED_URL="$NOTED_URL" \
    -e NOTED_PROJECT="$PROJECT" \
    "$DOCKER_IMAGE" \
    -v --tb=short --junitxml=/tests/results/api_e2e.xml "$@"

echo ""
echo "=== All test suites passed ==="
