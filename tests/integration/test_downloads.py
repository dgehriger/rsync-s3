"""
Integration tests for file downloads (current and snapshot versions)
"""

import pytest
import httpx


class TestDownloads:
    """Test file download functionality."""

    def test_download_current_version(self, browser_url, browser_auth):
        """Test downloading current version of a file."""
        response = httpx.get(
            f"{browser_url}/b/test-bucket/o/documents/document1.txt/download",
            auth=browser_auth,
        )
        assert response.status_code == 200
        content = response.text
        
        # Current version should have "CURRENT" in content
        assert "CURRENT version" in content
        print(f"✓ Downloaded current version: '{content.strip()}'")

    def test_download_current_version_explicit(self, browser_url, browser_auth):
        """Test downloading with explicit version=current parameter."""
        response = httpx.get(
            f"{browser_url}/b/test-bucket/o/documents/document1.txt/download",
            params={"version": "current"},
            auth=browser_auth,
        )
        assert response.status_code == 200
        content = response.text
        
        assert "CURRENT version" in content
        print("✓ Downloaded with explicit version=current")

    def test_download_snapshot_version_daily(self, browser_url, browser_auth):
        """Test downloading a daily snapshot version."""
        response = httpx.get(
            f"{browser_url}/b/test-bucket/o/documents/document1.txt/download",
            params={"version": "daily_2025-12-01"},
            auth=browser_auth,
        )
        assert response.status_code == 200
        content = response.text
        
        # Yesterday's version should have different content
        assert "YESTERDAY's version" in content
        print(f"✓ Downloaded daily snapshot: '{content.strip()}'")

    def test_download_snapshot_version_older(self, browser_url, browser_auth):
        """Test downloading an older snapshot version."""
        response = httpx.get(
            f"{browser_url}/b/test-bucket/o/documents/document1.txt/download",
            params={"version": "daily_2025-11-30"},
            auth=browser_auth,
        )
        assert response.status_code == 200
        content = response.text
        
        assert "ORIGINAL version" in content
        assert "Nov 30" in content
        print(f"✓ Downloaded older snapshot: '{content.strip()}'")

    def test_download_hourly_snapshot(self, browser_url, browser_auth):
        """Test downloading an hourly snapshot."""
        response = httpx.get(
            f"{browser_url}/b/test-bucket/o/documents/document1.txt/download",
            params={"version": "hourly_2025-12-01_14"},
            auth=browser_auth,
        )
        assert response.status_code == 200
        content = response.text
        
        assert "yesterday 2pm" in content
        print(f"✓ Downloaded hourly snapshot: '{content.strip()}'")

    def test_download_monthly_snapshot(self, browser_url, browser_auth):
        """Test downloading a monthly snapshot."""
        response = httpx.get(
            f"{browser_url}/b/test-bucket/o/documents/document1.txt/download",
            params={"version": "monthly_2025-11"},
            auth=browser_auth,
        )
        assert response.status_code == 200
        content = response.text
        
        assert "monthly snapshot November" in content
        print(f"✓ Downloaded monthly snapshot: '{content.strip()}'")

    def test_download_report_versions_differ(self, browser_url, browser_auth):
        """Test that report.txt has different content across versions."""
        # Current version
        current = httpx.get(
            f"{browser_url}/b/test-bucket/o/documents/report.txt/download",
            auth=browser_auth,
        ).text
        
        # Yesterday's version
        yesterday = httpx.get(
            f"{browser_url}/b/test-bucket/o/documents/report.txt/download",
            params={"version": "daily_2025-12-01"},
            auth=browser_auth,
        ).text
        
        # Older version
        older = httpx.get(
            f"{browser_url}/b/test-bucket/o/documents/report.txt/download",
            params={"version": "daily_2025-11-30"},
            auth=browser_auth,
        ).text
        
        # All should be different
        assert current != yesterday
        assert yesterday != older
        assert "v3" in current
        assert "v2" in yesterday
        assert "v1" in older
        print("✓ Report versions differ correctly: v1 → v2 → v3")

    def test_download_content_disposition(self, browser_url, browser_auth):
        """Test that downloads have correct Content-Disposition header."""
        response = httpx.get(
            f"{browser_url}/b/test-bucket/o/documents/document1.txt/download",
            auth=browser_auth,
        )
        assert response.status_code == 200
        
        content_disp = response.headers.get("content-disposition", "")
        assert "attachment" in content_disp
        assert "document1.txt" in content_disp
        print(f"✓ Content-Disposition header: {content_disp}")

    def test_download_nonexistent_version(self, browser_url, browser_auth):
        """Test downloading a nonexistent version returns error."""
        response = httpx.get(
            f"{browser_url}/b/test-bucket/o/documents/document1.txt/download",
            params={"version": "nonexistent_snapshot"},
            auth=browser_auth,
        )
        # Should fail (either 404 or 500 depending on implementation)
        assert response.status_code >= 400
        print("✓ Nonexistent version returns error")

    def test_download_file_not_in_snapshot(self, browser_url, browser_auth):
        """Test downloading a file that doesn't exist in a specific snapshot."""
        # photo.png doesn't exist in daily_2025-11-30
        response = httpx.get(
            f"{browser_url}/b/test-bucket/o/images/photo.png/download",
            params={"version": "daily_2025-11-30"},
            auth=browser_auth,
        )
        # Should fail
        assert response.status_code >= 400
        print("✓ File not in snapshot returns error")


class TestDownloadS3Direct:
    """Test downloads directly from S3 gateway."""

    def test_s3_download(self, s3_client):
        """Test S3 direct download."""
        response = s3_client.get_object(
            Bucket="test-bucket",
            Key="documents/document1.txt",
        )
        content = response["Body"].read().decode("utf-8")
        
        assert "CURRENT version" in content
        print("✓ S3 direct download works")

    def test_s3_download_binary(self, s3_client):
        """Test S3 download of binary-ish file."""
        response = s3_client.get_object(
            Bucket="test-bucket",
            Key="images/photo.png",
        )
        content = response["Body"].read()
        
        assert len(content) > 0
        print(f"✓ Downloaded binary file: {len(content)} bytes")
