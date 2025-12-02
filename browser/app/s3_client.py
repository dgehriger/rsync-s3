"""
S3 client integration using aioboto3
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Optional

import aioboto3
from botocore.config import Config as BotoConfig

from .config import Settings, get_settings


class S3Client:
    """Async S3 client for interacting with the rclone S3 gateway."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.session = aioboto3.Session()
        self._config = BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        )

    @asynccontextmanager
    async def _get_client(self):
        """Get an S3 client context manager."""
        async with self.session.client(
            "s3",
            endpoint_url=self.settings.s3_endpoint,
            aws_access_key_id=self.settings.s3_access_key,
            aws_secret_access_key=self.settings.s3_secret_key,
            config=self._config,
        ) as client:
            yield client

    async def list_buckets(self) -> list[dict[str, Any]]:
        """List all buckets (directories under s3root)."""
        async with self._get_client() as client:
            response = await client.list_buckets()
            buckets = []
            for bucket in response.get("Buckets", []):
                buckets.append(
                    {
                        "name": bucket["Name"],
                        "creation_date": bucket.get("CreationDate"),
                    }
                )
            return buckets

    async def list_objects(
        self,
        bucket: str,
        prefix: str = "",
        delimiter: str = "/",
        max_keys: int = 1000,
    ) -> dict[str, Any]:
        """
        List objects in a bucket with optional prefix.
        Returns both common prefixes (folders) and objects (files).
        """
        async with self._get_client() as client:
            params = {
                "Bucket": bucket,
                "MaxKeys": max_keys,
            }
            if prefix:
                params["Prefix"] = prefix
            if delimiter:
                params["Delimiter"] = delimiter

            response = await client.list_objects_v2(**params)

            # Extract folders (common prefixes)
            folders = []
            for prefix_info in response.get("CommonPrefixes", []):
                folder_prefix = prefix_info["Prefix"]
                # Get the folder name (last component before trailing slash)
                folder_name = folder_prefix.rstrip("/").split("/")[-1]
                folders.append(
                    {
                        "name": folder_name,
                        "prefix": folder_prefix,
                        "type": "folder",
                    }
                )

            # Extract files (objects)
            files = []
            for obj in response.get("Contents", []):
                key = obj["Key"]
                # Skip if this is the prefix itself (folder marker)
                if key == prefix:
                    continue
                name = key.split("/")[-1]
                if name:  # Skip empty names
                    files.append(
                        {
                            "name": name,
                            "key": key,
                            "size": obj.get("Size", 0),
                            "last_modified": obj.get("LastModified"),
                            "etag": obj.get("ETag", "").strip('"'),
                            "type": "file",
                        }
                    )

            return {
                "folders": folders,
                "files": files,
                "is_truncated": response.get("IsTruncated", False),
                "prefix": prefix,
            }

    async def head_object(self, bucket: str, key: str) -> Optional[dict[str, Any]]:
        """Get metadata for a specific object."""
        async with self._get_client() as client:
            try:
                response = await client.head_object(Bucket=bucket, Key=key)
                return {
                    "key": key,
                    "size": response.get("ContentLength", 0),
                    "last_modified": response.get("LastModified"),
                    "etag": response.get("ETag", "").strip('"'),
                    "content_type": response.get("ContentType", "application/octet-stream"),
                    "metadata": response.get("Metadata", {}),
                }
            except client.exceptions.ClientError:
                return None

    async def get_object_content(
        self, bucket: str, key: str
    ) -> AsyncIterator[bytes]:
        """Stream object content."""
        async with self._get_client() as client:
            response = await client.get_object(Bucket=bucket, Key=key)
            async with response["Body"] as stream:
                # Read in chunks
                while True:
                    chunk = await stream.read(65536)  # 64KB chunks
                    if not chunk:
                        break
                    yield chunk

    async def get_object_bytes(self, bucket: str, key: str) -> bytes:
        """Get entire object content as bytes."""
        async with self._get_client() as client:
            response = await client.get_object(Bucket=bucket, Key=key)
            async with response["Body"] as stream:
                return await stream.read()


# Global client instance
_s3_client: Optional[S3Client] = None


def get_s3_client() -> S3Client:
    """Get or create the global S3 client."""
    global _s3_client
    if _s3_client is None:
        _s3_client = S3Client()
    return _s3_client
