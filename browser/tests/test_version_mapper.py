"""
Unit tests for the version mapper
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import after path setup
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sftp_client import SnapshotInfo, FileInfo
from app.version_mapper import VersionInfo, VersionMapper, VersionSource


class TestSnapshotInfo:
    """Tests for SnapshotInfo parsing."""

    def test_parse_daily_snapshot(self):
        """Test parsing daily snapshot with date."""
        info = SnapshotInfo.from_name("daily_2025-12-01")
        assert info.name == "daily_2025-12-01"
        assert info.timestamp == datetime(2025, 12, 1)

    def test_parse_hourly_snapshot(self):
        """Test parsing hourly snapshot with date and hour."""
        info = SnapshotInfo.from_name("hourly_2025-12-01_14")
        assert info.name == "hourly_2025-12-01_14"
        assert info.timestamp == datetime(2025, 12, 1, 14, 0, 0)

    def test_parse_monthly_snapshot(self):
        """Test parsing monthly snapshot with year-month."""
        info = SnapshotInfo.from_name("monthly_2025-12")
        assert info.name == "monthly_2025-12"
        assert info.timestamp == datetime(2025, 12, 1)

    def test_parse_custom_prefix_snapshot(self):
        """Test parsing snapshot with custom prefix."""
        info = SnapshotInfo.from_name("custom_backup_2025-11-15")
        assert info.name == "custom_backup_2025-11-15"
        assert info.timestamp == datetime(2025, 11, 15)

    def test_parse_unknown_format(self):
        """Test parsing snapshot with unrecognized format."""
        info = SnapshotInfo.from_name("random_snapshot_name")
        assert info.name == "random_snapshot_name"
        assert info.timestamp is None


class TestVersionInfo:
    """Tests for VersionInfo."""

    def test_to_dict_current(self):
        """Test converting current version to dict."""
        version = VersionInfo(
            version_id="current",
            source=VersionSource.CURRENT,
            size=1024,
            modified_time=datetime(2025, 12, 1, 10, 30, 0),
            etag="abc123",
            is_current=True,
        )
        d = version.to_dict()
        assert d["version_id"] == "current"
        assert d["source"] == "current"
        assert d["size"] == 1024
        assert d["is_current"] is True
        assert "2025-12-01" in d["modified_time"]

    def test_to_dict_snapshot(self):
        """Test converting snapshot version to dict."""
        version = VersionInfo(
            version_id="daily_2025-12-01",
            source=VersionSource.SNAPSHOT,
            size=2048,
            modified_time=datetime(2025, 12, 1),
            snapshot_name="daily_2025-12-01",
            is_current=False,
        )
        d = version.to_dict()
        assert d["version_id"] == "daily_2025-12-01"
        assert d["source"] == "snapshot"
        assert d["snapshot_name"] == "daily_2025-12-01"
        assert d["is_current"] is False


class TestVersionMapper:
    """Tests for VersionMapper."""

    @pytest.fixture
    def mock_s3_client(self):
        """Create a mock S3 client."""
        client = MagicMock()
        client.head_object = AsyncMock()
        client.get_object_bytes = AsyncMock()
        return client

    @pytest.fixture
    def mock_sftp_client(self):
        """Create a mock SFTP client."""
        client = MagicMock()
        client.list_snapshots = AsyncMock()
        client.stat_snapshot_object = AsyncMock()
        client.get_snapshot_file_bytes = AsyncMock()
        return client

    @pytest.fixture
    def mapper(self, mock_s3_client, mock_sftp_client):
        """Create a VersionMapper with mocks."""
        return VersionMapper(
            s3_client=mock_s3_client,
            sftp_client=mock_sftp_client,
        )

    @pytest.mark.asyncio
    async def test_list_versions_current_only(self, mapper, mock_s3_client, mock_sftp_client):
        """Test listing versions when only current exists."""
        mock_s3_client.head_object.return_value = {
            "size": 1024,
            "last_modified": datetime(2025, 12, 1),
            "etag": "abc123",
        }
        mock_sftp_client.list_snapshots.return_value = []

        versions = await mapper.list_object_versions("test-bucket", "test/key.txt")

        assert len(versions) == 1
        assert versions[0].version_id == "current"
        assert versions[0].is_current is True

    @pytest.mark.asyncio
    async def test_list_versions_with_snapshots(self, mapper, mock_s3_client, mock_sftp_client):
        """Test listing versions with snapshots."""
        mock_s3_client.head_object.return_value = {
            "size": 1024,
            "last_modified": datetime(2025, 12, 2),
            "etag": "abc123",
        }
        mock_sftp_client.list_snapshots.return_value = [
            SnapshotInfo("daily_2025-12-01", datetime(2025, 12, 1)),
            SnapshotInfo("daily_2025-11-30", datetime(2025, 11, 30)),
        ]
        mock_sftp_client.stat_snapshot_object.return_value = FileInfo(
            path="/path/to/file",
            name="key.txt",
            size=1000,
            modified_time=datetime(2025, 12, 1),
            is_dir=False,
        )

        versions = await mapper.list_object_versions("test-bucket", "test/key.txt")

        assert len(versions) == 3
        # Should be sorted by time descending
        assert versions[0].is_current is True
        assert versions[1].snapshot_name == "daily_2025-12-01"
        assert versions[2].snapshot_name == "daily_2025-11-30"

    @pytest.mark.asyncio
    async def test_list_versions_file_not_in_snapshot(self, mapper, mock_s3_client, mock_sftp_client):
        """Test that versions are skipped if file doesn't exist in snapshot."""
        mock_s3_client.head_object.return_value = {
            "size": 1024,
            "last_modified": datetime(2025, 12, 2),
            "etag": "abc123",
        }
        mock_sftp_client.list_snapshots.return_value = [
            SnapshotInfo("daily_2025-12-01", datetime(2025, 12, 1)),
        ]
        mock_sftp_client.stat_snapshot_object.return_value = None

        versions = await mapper.list_object_versions("test-bucket", "test/key.txt")

        assert len(versions) == 1
        assert versions[0].is_current is True

    @pytest.mark.asyncio
    async def test_get_version_content_current(self, mapper, mock_s3_client):
        """Test getting content of current version."""
        mock_s3_client.get_object_bytes.return_value = b"file content"
        mock_s3_client.head_object.return_value = {
            "size": 12,
            "last_modified": datetime(2025, 12, 1),
            "etag": "abc123",
        }

        content, version_info = await mapper.get_version_content(
            "test-bucket", "test/key.txt", "current"
        )

        assert content == b"file content"
        assert version_info.is_current is True
        mock_s3_client.get_object_bytes.assert_called_once_with("test-bucket", "test/key.txt")

    @pytest.mark.asyncio
    async def test_get_version_content_snapshot(self, mapper, mock_sftp_client):
        """Test getting content of snapshot version."""
        mock_sftp_client.get_snapshot_file_bytes.return_value = b"old content"
        mock_sftp_client.stat_snapshot_object.return_value = FileInfo(
            path="/path",
            name="key.txt",
            size=11,
            modified_time=datetime(2025, 11, 30),
            is_dir=False,
        )

        content, version_info = await mapper.get_version_content(
            "test-bucket", "test/key.txt", "daily_2025-11-30"
        )

        assert content == b"old content"
        assert version_info.is_current is False
        assert version_info.snapshot_name == "daily_2025-11-30"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
