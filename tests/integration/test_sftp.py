"""
Integration tests for SFTP connectivity and snapshot access
"""

import pytest
import asyncio
import asyncssh


class TestSFTPConnectivity:
    """Test direct SFTP access to mock rsync.net."""

    @pytest.mark.asyncio
    async def test_sftp_connect(self, sftp_config):
        """Test basic SFTP connection."""
        async with asyncssh.connect(**sftp_config) as conn:
            async with conn.start_sftp_client() as sftp:
                # List home directory
                entries = await sftp.listdir(".")
                assert "s3root" in entries
                assert ".zfs" in entries
                print(f"✓ SFTP connected, home contains: {entries}")

    @pytest.mark.asyncio
    async def test_list_s3root_buckets(self, sftp_config):
        """Test listing buckets via SFTP."""
        async with asyncssh.connect(**sftp_config) as conn:
            async with conn.start_sftp_client() as sftp:
                entries = await sftp.listdir("s3root")
                assert "test-bucket" in entries
                assert "backup-bucket" in entries
                assert "empty-bucket" in entries
                print(f"✓ SFTP s3root buckets: {entries}")

    @pytest.mark.asyncio
    async def test_list_zfs_snapshots(self, sftp_config):
        """Test listing .zfs snapshots via SFTP."""
        async with asyncssh.connect(**sftp_config) as conn:
            async with conn.start_sftp_client() as sftp:
                entries = await sftp.listdir(".zfs")
                assert "daily_2025-12-01" in entries
                assert "daily_2025-11-30" in entries
                assert "hourly_2025-12-01_14" in entries
                assert "monthly_2025-11" in entries
                print(f"✓ SFTP .zfs snapshots: {entries}")

    @pytest.mark.asyncio
    async def test_read_current_file(self, sftp_config):
        """Test reading current file via SFTP."""
        async with asyncssh.connect(**sftp_config) as conn:
            async with conn.start_sftp_client() as sftp:
                async with sftp.open("s3root/test-bucket/documents/document1.txt", "r") as f:
                    content = await f.read()
                
                assert "CURRENT version" in content
                print(f"✓ SFTP read current: '{content.strip()}'")

    @pytest.mark.asyncio
    async def test_read_snapshot_file(self, sftp_config):
        """Test reading snapshot file via SFTP."""
        async with asyncssh.connect(**sftp_config) as conn:
            async with conn.start_sftp_client() as sftp:
                path = ".zfs/daily_2025-12-01/s3root/test-bucket/documents/document1.txt"
                async with sftp.open(path, "r") as f:
                    content = await f.read()
                
                assert "YESTERDAY's version" in content
                print(f"✓ SFTP read snapshot: '{content.strip()}'")

    @pytest.mark.asyncio
    async def test_stat_file(self, sftp_config):
        """Test getting file stats via SFTP."""
        async with asyncssh.connect(**sftp_config) as conn:
            async with conn.start_sftp_client() as sftp:
                attrs = await sftp.stat("s3root/test-bucket/documents/document1.txt")
                
                assert attrs.size > 0
                assert attrs.mtime is not None
                print(f"✓ SFTP stat: size={attrs.size}, mtime={attrs.mtime}")

    @pytest.mark.asyncio
    async def test_snapshot_has_s3root(self, sftp_config):
        """Test that valid snapshots have s3root directory."""
        async with asyncssh.connect(**sftp_config) as conn:
            async with conn.start_sftp_client() as sftp:
                # Valid snapshot should have s3root
                entries = await sftp.listdir(".zfs/daily_2025-12-01")
                assert "s3root" in entries
                
                # system_snapshot_ignored should NOT have s3root
                entries = await sftp.listdir(".zfs/system_snapshot_ignored")
                assert "s3root" not in entries
                print("✓ Snapshot s3root detection works")

    @pytest.mark.asyncio
    async def test_file_not_in_old_snapshot(self, sftp_config):
        """Test that newer files don't exist in older snapshots."""
        async with asyncssh.connect(**sftp_config) as conn:
            async with conn.start_sftp_client() as sftp:
                # photo.png exists in current
                attrs = await sftp.stat("s3root/test-bucket/images/photo.png")
                assert attrs is not None
                
                # photo.png exists in yesterday's snapshot
                attrs = await sftp.stat(".zfs/daily_2025-12-01/s3root/test-bucket/images/photo.png")
                assert attrs is not None
                
                # photo.png does NOT exist in older snapshot
                try:
                    await sftp.stat(".zfs/daily_2025-11-30/s3root/test-bucket/images/photo.png")
                    pytest.fail("Expected file to not exist")
                except asyncssh.SFTPError:
                    pass  # Expected
                
                print("✓ File existence varies across snapshots correctly")
