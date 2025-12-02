"""
Integration test configuration and fixtures
"""

import os
import asyncio
import pytest
import boto3
from botocore.config import Config as BotoConfig


# Environment configuration
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://localhost:9000")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "testkey")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "testsecret")
BROWSER_URL = os.environ.get("BROWSER_URL", "http://localhost:8080")
BROWSER_USER = os.environ.get("BROWSER_USER", "testadmin")
BROWSER_PASS = os.environ.get("BROWSER_PASS", "testpass")
SFTP_HOST = os.environ.get("SFTP_HOST", "localhost")
SFTP_USER = os.environ.get("SFTP_USER", "testuser")
SSH_KEY_PATH = os.environ.get("SSH_KEY_PATH", "./tests/secrets/test_key")


@pytest.fixture(scope="session")
def s3_client():
    """Create S3 client for testing."""
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        config=BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )


@pytest.fixture(scope="session")
def browser_auth():
    """Browser authentication tuple."""
    return (BROWSER_USER, BROWSER_PASS)


@pytest.fixture(scope="session")
def browser_url():
    """Browser base URL."""
    return BROWSER_URL


@pytest.fixture(scope="session")
def sftp_config():
    """SFTP connection configuration."""
    return {
        "host": SFTP_HOST,
        "username": SFTP_USER,
        "client_keys": [SSH_KEY_PATH],
        "known_hosts": None,
    }
