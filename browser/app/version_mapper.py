"""
Version mapping - combines S3 current state with ZFS snapshot history
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from .config import Settings, get_settings
from .s3_client import S3Client, get_s3_client
from .sftp_client import SFTPClient, SnapshotInfo, get_sftp_client


def _normalize_datetime(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize datetime to seconds precision for comparison.
    
    S3 returns datetimes with microseconds, SFTP returns integer seconds.
    Truncate to seconds to ensure proper comparison.
    """
    if dt is None:
        return None
    return dt.replace(microsecond=0)


class VersionSource(str, Enum):
    """Source of an object version."""

    CURRENT = "current"
    SNAPSHOT = "snapshot"


@dataclass
class VersionInfo:
    """Information about an object version."""

    version_id: str
    source: VersionSource
    size: int
    modified_time: Optional[datetime]
    etag: Optional[str] = None
    snapshot_name: Optional[str] = None
    is_current: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "version_id": self.version_id,
            "source": self.source.value,
            "size": self.size,
            "modified_time": (
                self.modified_time.isoformat() if self.modified_time else None
            ),
            "etag": self.etag,
            "snapshot_name": self.snapshot_name,
            "is_current": self.is_current,
        }


class VersionMapper:
    """Maps object versions across S3 current state and ZFS snapshots."""

    def __init__(
        self,
        s3_client: Optional[S3Client] = None,
        sftp_client: Optional[SFTPClient] = None,
        settings: Optional[Settings] = None,
    ):
        self.s3_client = s3_client or get_s3_client()
        self.sftp_client = sftp_client or get_sftp_client()
        self.settings = settings or get_settings()

    async def list_object_versions(
        self, bucket: str, key: str
    ) -> list[VersionInfo]:
        """
        List all unique versions of an object, including current and snapshots.
        
        Strategy:
        - Current (live) version is always shown if it exists
        - Snapshots are shown only when they represent a DIFFERENT version
        - If current matches snapshots, we show "live" as the source (not a snapshot)
        - Historical versions show the OLDEST snapshot that has that version

        Returns versions sorted newest first, with sequential IDs (v1 = oldest).
        """
        # Get current version from S3
        current_task = asyncio.create_task(
            self._get_current_version(bucket, key)
        )

        # Get available snapshots
        snapshots = await self.sftp_client.list_snapshots()

        # Check each snapshot for this object (in parallel, limited concurrency)
        semaphore = asyncio.Semaphore(10)  # Limit concurrent SFTP operations

        async def check_snapshot(snapshot: SnapshotInfo) -> Optional[VersionInfo]:
            async with semaphore:
                return await self._get_snapshot_version(bucket, key, snapshot)

        snapshot_tasks = [check_snapshot(snap) for snap in snapshots]

        # Wait for current version
        current_version = await current_task

        # Wait for snapshot checks
        snapshot_results = await asyncio.gather(*snapshot_tasks)
        snapshot_versions = [v for v in snapshot_results if v]

        # Sort snapshots by file mtime ascending (oldest file version first)
        snapshot_versions.sort(
            key=lambda v: (
                v.modified_time or datetime.min.replace(tzinfo=timezone.utc),
            ),
        )

        # Build unique versions list
        # Key insight: if current exists, we want to show it as "live" 
        # and only show snapshots that have DIFFERENT content
        unique_versions: list[VersionInfo] = []
        seen_signatures: set[tuple[int, Optional[datetime]]] = set()
        
        # First, determine current version's signature (normalized to seconds)
        current_signature: Optional[tuple[int, Optional[datetime]]] = None
        if current_version:
            current_signature = (
                current_version.size,
                _normalize_datetime(current_version.modified_time),
            )

        # Process snapshots oldest-first, keeping first occurrence of each unique version
        for version in snapshot_versions:
            signature = (version.size, _normalize_datetime(version.modified_time))
            
            # Skip if we've seen this version before
            if signature in seen_signatures:
                continue
                
            # Skip if this matches current (we'll show current as "live" instead)
            if signature == current_signature:
                continue
                
            seen_signatures.add(signature)
            unique_versions.append(version)

        # Add current version last (it's the newest)
        if current_version:
            unique_versions.append(current_version)

        # Assign sequential version IDs (v1, v2, ...) from oldest to newest
        for i, version in enumerate(unique_versions, start=1):
            if version.is_current:
                version.version_id = f"v{i} (current)"
            else:
                version.version_id = f"v{i}"

        # Return newest first for display
        return list(reversed(unique_versions))

    async def _get_current_version(
        self, bucket: str, key: str
    ) -> Optional[VersionInfo]:
        """Get the current version of an object from S3."""
        metadata = await self.s3_client.head_object(bucket, key)
        if metadata:
            return VersionInfo(
                version_id="current",
                source=VersionSource.CURRENT,
                size=metadata["size"],
                modified_time=metadata["last_modified"],
                etag=metadata["etag"],
                snapshot_name=None,
                is_current=True,
            )
        return None

    async def _get_snapshot_version(
        self, bucket: str, key: str, snapshot: SnapshotInfo
    ) -> Optional[VersionInfo]:
        """Get version info for an object in a specific snapshot."""
        file_info = await self.sftp_client.stat_snapshot_object(
            snapshot.name, bucket, key
        )
        if file_info and not file_info.is_dir:
            return VersionInfo(
                version_id=snapshot.name,
                source=VersionSource.SNAPSHOT,
                size=file_info.size,
                modified_time=file_info.modified_time,
                etag=None,  # Snapshots don't have ETags
                snapshot_name=snapshot.name,
                is_current=False,
            )
        return None

    async def get_version_content(
        self, bucket: str, key: str, version_id: str
    ) -> tuple[bytes, VersionInfo]:
        """
        Get the content of a specific version.

        Returns tuple of (content_bytes, version_info).
        """
        if version_id == "current" or version_id.endswith("(current)"):
            # Get from S3
            content = await self.s3_client.get_object_bytes(bucket, key)
            metadata = await self.s3_client.head_object(bucket, key)
            version_info = VersionInfo(
                version_id="current",
                source=VersionSource.CURRENT,
                size=len(content),
                modified_time=metadata["last_modified"] if metadata else None,
                etag=metadata["etag"] if metadata else None,
                is_current=True,
            )
            return content, version_info
        else:
            # Get from snapshot
            content = await self.sftp_client.get_snapshot_file_bytes(
                version_id, bucket, key
            )
            file_info = await self.sftp_client.stat_snapshot_object(
                version_id, bucket, key
            )
            version_info = VersionInfo(
                version_id=version_id,
                source=VersionSource.SNAPSHOT,
                size=len(content),
                modified_time=file_info.modified_time if file_info else None,
                snapshot_name=version_id,
                is_current=False,
            )
            return content, version_info


# Global mapper instance
_version_mapper: Optional[VersionMapper] = None


def get_version_mapper() -> VersionMapper:
    """Get or create the global version mapper."""
    global _version_mapper
    if _version_mapper is None:
        _version_mapper = VersionMapper()
    return _version_mapper
