"""
Configuration settings using Pydantic
"""

import logging
from functools import lru_cache
from typing import Optional

import yaml
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


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

    # Remote config settings
    remote_config_path: str = ".config/rsync-s3/rsync-s3.yml"

    # Pagination defaults
    default_page_size: int = 20
    page_size_options: list[int] = [20, 50, 100]

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


class RemoteConfig:
    """Remote configuration loaded from rsync.net via SFTP."""

    def __init__(self):
        self.exposed_folders: list[str] = []  # Empty means show all
        self.hidden_folders: list[str] = [".ssh", ".zfs", ".config"]  # Always hidden by default
        self._loaded: bool = False

    def filter_buckets(self, buckets: list[dict]) -> list[dict]:
        """Filter buckets based on configuration."""
        if not self._loaded:
            return buckets

        filtered = []
        for bucket in buckets:
            name = bucket.get("name", "")
            
            # Always hide folders in hidden_folders list
            if name in self.hidden_folders:
                continue
            
            # If exposed_folders is set, only show those
            if self.exposed_folders:
                if name in self.exposed_folders:
                    filtered.append(bucket)
            else:
                # No explicit exposure list, show all except hidden
                filtered.append(bucket)
        
        return filtered

    def load_from_yaml(self, content: str) -> None:
        """Load configuration from YAML content."""
        try:
            data = yaml.safe_load(content)
            if not data:
                return
            
            # Handle exposed folders
            if "exposed_folders" in data:
                folders = data["exposed_folders"]
                if isinstance(folders, list):
                    self.exposed_folders = [str(f) for f in folders]
            
            # Handle hidden folders (extends defaults)
            if "hidden_folders" in data:
                folders = data["hidden_folders"]
                if isinstance(folders, list):
                    # Extend the default hidden folders
                    for f in folders:
                        if str(f) not in self.hidden_folders:
                            self.hidden_folders.append(str(f))
            
            self._loaded = True
            logger.info(
                f"Remote config loaded: exposed={self.exposed_folders}, hidden={self.hidden_folders}"
            )
        except yaml.YAMLError as e:
            logger.warning(f"Failed to parse remote config YAML: {e}")


# Global remote config instance
_remote_config: Optional[RemoteConfig] = None


def get_remote_config() -> RemoteConfig:
    """Get the global remote config instance."""
    global _remote_config
    if _remote_config is None:
        _remote_config = RemoteConfig()
    return _remote_config


async def load_remote_config_from_sftp(sftp_client) -> RemoteConfig:
    """Load remote config from rsync.net via SFTP."""
    config = get_remote_config()
    settings = get_settings()
    
    if config._loaded:
        return config
    
    try:
        async with sftp_client.get_sftp() as sftp:
            try:
                content = await sftp.open(settings.remote_config_path, "r")
                yaml_content = await content.read()
                await content.close()
                config.load_from_yaml(yaml_content.decode("utf-8") if isinstance(yaml_content, bytes) else yaml_content)
            except Exception as e:
                logger.info(f"Remote config not found or unreadable at {settings.remote_config_path}: {e}")
                # Set as loaded with defaults so we don't keep trying
                config._loaded = True
    except Exception as e:
        logger.warning(f"Failed to connect for remote config: {e}")
        config._loaded = True
    
    return config
