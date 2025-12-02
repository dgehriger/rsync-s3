"""
SFTP client integration using asyncssh for accessing rsync.net snapshots
"""

import asyncio
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, AsyncIterator, Optional

import asyncssh

from .config import Settings, get_settings


@dataclass
class SnapshotInfo:
    """Information about a ZFS snapshot."""

    name: str
    timestamp: Optional[datetime] = None

    @classmethod
    def from_name(cls, name: str) -> "SnapshotInfo":
        """Parse snapshot name and extract timestamp if possible."""
        timestamp = None

        # Try to parse common snapshot naming patterns
        # Examples: daily_2025-12-01, hourly_2025-12-01_14, monthly_2025-12
        patterns = [
            r".*_(\d{4}-\d{2}-\d{2})_(\d{2})",  # date with hour
            r".*_(\d{4}-\d{2}-\d{2})",  # date only
            r".*_(\d{4}-\d{2})",  # year-month only
        ]

        for pattern in patterns:
            match = re.search(pattern, name)
            if match:
                try:
                    groups = match.groups()
                    if len(groups) == 2:
                        # Date with hour
                        timestamp = datetime.strptime(
                            f"{groups[0]}_{groups[1]}", "%Y-%m-%d_%H"
                        )
                    elif len(groups) == 1:
                        date_str = groups[0]
                        if len(date_str) == 10:  # YYYY-MM-DD
                            timestamp = datetime.strptime(date_str, "%Y-%m-%d")
                        elif len(date_str) == 7:  # YYYY-MM
                            timestamp = datetime.strptime(date_str, "%Y-%m")
                    break
                except ValueError:
                    pass

        return cls(name=name, timestamp=timestamp)


@dataclass
class FileInfo:
    """Information about a file from SFTP."""

    path: str
    name: str
    size: int
    modified_time: datetime
    is_dir: bool


class SFTPClient:
    """Async SFTP client for accessing rsync.net ZFS snapshots."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._connection: Optional[asyncssh.SSHClientConnection] = None

    async def connect(self) -> asyncssh.SSHClientConnection:
        """Establish SSH connection to rsync.net."""
        return await asyncssh.connect(
            self.settings.rsync_host,
            username=self.settings.rsync_user,
            client_keys=[self.settings.ssh_key_path],
            known_hosts=None,  # In production, use proper host key verification
        )

    @asynccontextmanager
    async def get_sftp(self):
        """Get an SFTP client context manager."""
        conn = await self.connect()
        try:
            sftp = await conn.start_sftp_client()
            yield sftp
        finally:
            conn.close()
            await conn.wait_closed()

    def _snapshot_base_path(self) -> str:
        """Get the base path for ZFS snapshots."""
        return f"{self.settings.snapshot_dir}"

    def _snapshot_root(self, snapshot_name: str) -> str:
        """Get the root path for a specific snapshot's S3 data."""
        if self.settings.s3_root_prefix in (".", ""):
            return f"{self._snapshot_base_path()}/{snapshot_name}"
        return f"{self._snapshot_base_path()}/{snapshot_name}/{self.settings.s3_root_prefix}"

    def _snapshot_object_path(
        self, snapshot_name: str, bucket: str, key: str
    ) -> str:
        """Get the full path to an object within a snapshot."""
        return f"{self._snapshot_root(snapshot_name)}/{bucket}/{key}"

    async def list_snapshots(self) -> list[SnapshotInfo]:
        """List all available ZFS snapshots."""
        snapshots = []
        async with self.get_sftp() as sftp:
            try:
                entries = await sftp.readdir(self._snapshot_base_path())
                for entry in entries:
                    if entry.filename.startswith("."):
                        continue
                    # Verify it's a directory
                    try:
                        snapshot_path = f"{self._snapshot_base_path()}/{entry.filename}"
                        if self.settings.s3_root_prefix not in (".", ""):
                            snapshot_path = f"{snapshot_path}/{self.settings.s3_root_prefix}"
                        attrs = await sftp.stat(snapshot_path)
                        if attrs.type == asyncssh.FILEXFER_TYPE_DIRECTORY:
                            snapshots.append(
                                SnapshotInfo.from_name(entry.filename)
                            )
                    except (asyncssh.SFTPError, OSError):
                        # Skip snapshots without the required path
                        pass
            except (asyncssh.SFTPError, OSError):
                # .zfs directory might not exist or be accessible
                pass

        # Sort by timestamp descending (newest first), None timestamps last
        snapshots.sort(
            key=lambda s: (s.timestamp is not None, s.timestamp),
            reverse=True,
        )
        return snapshots

    async def stat_snapshot_object(
        self, snapshot_name: str, bucket: str, key: str
    ) -> Optional[FileInfo]:
        """Get file info for an object within a snapshot."""
        path = self._snapshot_object_path(snapshot_name, bucket, key)
        async with self.get_sftp() as sftp:
            try:
                attrs = await sftp.stat(path)
                return FileInfo(
                    path=path,
                    name=PurePosixPath(key).name,
                    size=attrs.size or 0,
                    modified_time=datetime.fromtimestamp(attrs.mtime or 0, tz=timezone.utc),
                    is_dir=attrs.type == asyncssh.FILEXFER_TYPE_DIRECTORY,
                )
            except (asyncssh.SFTPError, OSError):
                return None

    async def object_exists_in_snapshot(
        self, snapshot_name: str, bucket: str, key: str
    ) -> bool:
        """Check if an object exists in a specific snapshot."""
        info = await self.stat_snapshot_object(snapshot_name, bucket, key)
        return info is not None and not info.is_dir

    async def open_snapshot_file_stream(
        self, snapshot_name: str, bucket: str, key: str
    ) -> AsyncIterator[bytes]:
        """Stream file content from a snapshot."""
        path = self._snapshot_object_path(snapshot_name, bucket, key)
        async with self.get_sftp() as sftp:
            async with sftp.open(path, "rb") as f:
                while True:
                    chunk = await f.read(65536)  # 64KB chunks
                    if not chunk:
                        break
                    yield chunk

    async def get_snapshot_file_bytes(
        self, snapshot_name: str, bucket: str, key: str
    ) -> bytes:
        """Get entire file content from a snapshot as bytes."""
        path = self._snapshot_object_path(snapshot_name, bucket, key)
        async with self.get_sftp() as sftp:
            async with sftp.open(path, "rb") as f:
                return await f.read()

    async def list_snapshot_objects(
        self, snapshot_name: str, bucket: str, prefix: str = ""
    ) -> list[FileInfo]:
        """List objects in a snapshot bucket/prefix."""
        base_path = f"{self._snapshot_root(snapshot_name)}/{bucket}"
        if prefix:
            base_path = f"{base_path}/{prefix.rstrip('/')}"

        objects = []
        async with self.get_sftp() as sftp:
            try:
                entries = await sftp.readdir(base_path)
                for entry in entries:
                    if entry.filename.startswith("."):
                        continue
                    full_path = f"{base_path}/{entry.filename}"
                    key = f"{prefix}{entry.filename}" if prefix else entry.filename
                    objects.append(
                        FileInfo(
                            path=full_path,
                            name=entry.filename,
                            size=entry.attrs.size or 0,
                            modified_time=datetime.fromtimestamp(
                                entry.attrs.mtime or 0, tz=timezone.utc
                            ),
                            is_dir=entry.attrs.type
                            == asyncssh.FILEXFER_TYPE_DIRECTORY,
                        )
                    )
            except (asyncssh.SFTPError, OSError):
                pass

        return objects


# Global client instance
_sftp_client: Optional[SFTPClient] = None


def get_sftp_client() -> SFTPClient:
    """Get or create the global SFTP client."""
    global _sftp_client
    if _sftp_client is None:
        _sftp_client = SFTPClient()
    return _sftp_client
