"""
Test configuration and fixtures
"""

import pytest


@pytest.fixture
def sample_bucket_name():
    """Sample bucket name for testing."""
    return "test-bucket"


@pytest.fixture
def sample_key():
    """Sample object key for testing."""
    return "folder/subfolder/file.txt"
