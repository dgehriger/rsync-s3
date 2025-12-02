# Test runner container for integration tests
FROM python:3.12-slim

WORKDIR /tests

# Install test dependencies
RUN pip install --no-cache-dir \
    pytest \
    pytest-asyncio \
    httpx \
    boto3 \
    asyncssh \
    rich

# Default command runs tests (files mounted at runtime)
CMD ["pytest", "-v", "--tb=short", "/tests/integration/"]
