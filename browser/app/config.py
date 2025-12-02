"""
Configuration settings using Pydantic
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # S3 Gateway settings
    s3_endpoint: str = "http://s3-gateway:9000"
    s3_public_endpoint: str = ""  # Public S3 endpoint URL for display (e.g., https://s3.example.com:8443)
    s3_access_key: str = ""
    s3_secret_key: str = ""

    # Rsync.net SFTP settings
    rsync_host: str = ""
    rsync_user: str = ""
    ssh_key_path: str = "/secrets/rsync_id_ed25519"

    # Snapshot settings
    snapshot_dir: str = ".zfs"
    s3_root_prefix: str = "s3root"

    # Authentication settings
    auth_username: str = "admin"
    auth_password: str = "changeme"
    auth_mode: str = "basic"  # "basic", "cloudflare", or "none"

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
