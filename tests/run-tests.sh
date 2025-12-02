#!/bin/bash
# Run integration tests for the rsync-s3 project

set -e

echo "=========================================="
echo "  Rsync.net S3 Gateway Integration Tests"
echo "=========================================="
echo ""

# Change to project directory
cd "$(dirname "$0")/.."

# Build and start test containers
echo "▶ Building and starting test containers..."
docker-compose -f docker-compose.test.yml build
docker-compose -f docker-compose.test.yml up -d mock-rsync s3-gateway browser

# Wait for services to be ready
echo "▶ Waiting for services to start..."
sleep 10

# Check health
echo "▶ Checking service health..."
docker-compose -f docker-compose.test.yml ps

# Run tests
echo ""
echo "▶ Running integration tests..."
docker-compose -f docker-compose.test.yml run --rm test-runner

# Capture exit code
TEST_EXIT_CODE=$?

# Cleanup
echo ""
echo "▶ Cleaning up..."
docker-compose -f docker-compose.test.yml down -v

# Report
echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "=========================================="
    echo "  ✅ All tests passed!"
    echo "=========================================="
else
    echo "=========================================="
    echo "  ❌ Some tests failed"
    echo "=========================================="
fi

exit $TEST_EXIT_CODE
