"""
Unit tests for SFTP client
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sftp_client import SnapshotInfo, FileInfo, SFTPClient


class TestSnapshotPathResolution:
    """Tests for snapshot path resolution."""

    @pytest.fixture
    def sftp_client(self):
        """Create SFTP client with mock settings."""
        settings = MagicMock()
        settings.rsync_host = "test.rsync.net"
        settings.rsync_user = "testuser"
        settings.ssh_key_path = "/path/to/key"
        settings.snapshot_dir = ".zfs"
        settings.s3_root_prefix = "s3root"
        return SFTPClient(settings)

    def test_snapshot_base_path(self, sftp_client):
        """Test base path for snapshots."""
        assert sftp_client._snapshot_base_path() == ".zfs"

    def test_snapshot_root(self, sftp_client):
        """Test root path for a specific snapshot."""
        path = sftp_client._snapshot_root("daily_2025-12-01")
        assert path == ".zfs/daily_2025-12-01/s3root"

    def test_snapshot_object_path(self, sftp_client):
        """Test full path to an object in a snapshot."""
        path = sftp_client._snapshot_object_path(
            "daily_2025-12-01", "my-bucket", "folder/file.txt"
        )
        assert path == ".zfs/daily_2025-12-01/s3root/my-bucket/folder/file.txt"

    def test_snapshot_object_path_no_folder(self, sftp_client):
        """Test path for object at bucket root."""
        path = sftp_client._snapshot_object_path(
            "hourly_2025-12-01_10", "bucket", "file.txt"
        )
        assert path == ".zfs/hourly_2025-12-01_10/s3root/bucket/file.txt"


class TestSnapshotInfoParsing:
    """Additional tests for snapshot info parsing edge cases."""

    def test_parse_multiple_underscores(self):
        """Test parsing snapshot with multiple underscores."""
        info = SnapshotInfo.from_name("auto_daily_backup_2025-06-15")
        assert info.name == "auto_daily_backup_2025-06-15"
        assert info.timestamp == datetime(2025, 6, 15)

    def test_parse_numeric_only(self):
        """Test parsing snapshot with only numbers."""
        info = SnapshotInfo.from_name("20251201")
        assert info.name == "20251201"
        assert info.timestamp is None  # Not matching expected pattern

    def test_parse_empty_string(self):
        """Test parsing empty snapshot name."""
        info = SnapshotInfo.from_name("")
        assert info.name == ""
        assert info.timestamp is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
