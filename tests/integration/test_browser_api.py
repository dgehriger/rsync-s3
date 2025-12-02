"""
Integration tests for Browser API and snapshot version discovery
"""

import pytest
import httpx


class TestBrowserAPI:
    """Test browser API endpoints."""

    def test_health_check(self, browser_url):
        """Test health endpoint is accessible."""
        response = httpx.get(f"{browser_url}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print("✓ Health check passed")

    def test_list_buckets_api(self, browser_url, browser_auth):
        """Test API bucket listing."""
        response = httpx.get(
            f"{browser_url}/api/buckets",
            auth=browser_auth,
        )
        assert response.status_code == 200
        data = response.json()
        
        bucket_names = [b["name"] for b in data["buckets"]]
        assert "test-bucket" in bucket_names
        assert "backup-bucket" in bucket_names
        print(f"✓ API returned buckets: {bucket_names}")

    def test_list_objects_api(self, browser_url, browser_auth):
        """Test API object listing."""
        response = httpx.get(
            f"{browser_url}/api/b/test-bucket",
            auth=browser_auth,
        )
        assert response.status_code == 200
        data = response.json()
        
        folder_names = [f["name"] for f in data["folders"]]
        assert "documents" in folder_names
        assert "images" in folder_names
        print(f"✓ API returned folders: {folder_names}")

    def test_list_objects_with_prefix_api(self, browser_url, browser_auth):
        """Test API object listing with prefix."""
        response = httpx.get(
            f"{browser_url}/api/b/test-bucket",
            params={"prefix": "documents/"},
            auth=browser_auth,
        )
        assert response.status_code == 200
        data = response.json()
        
        file_names = [f["name"] for f in data["files"]]
        assert "document1.txt" in file_names
        assert "report.txt" in file_names
        print(f"✓ API returned files: {file_names}")

    def test_object_detail_api(self, browser_url, browser_auth):
        """Test API object detail."""
        response = httpx.get(
            f"{browser_url}/api/b/test-bucket/o/documents/document1.txt",
            auth=browser_auth,
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["key"] == "documents/document1.txt"
        assert data["size"] > 0
        print(f"✓ Object detail: key={data['key']}, size={data['size']}")

    def test_list_snapshots_api(self, browser_url, browser_auth):
        """Test API snapshot listing."""
        response = httpx.get(
            f"{browser_url}/api/snapshots",
            auth=browser_auth,
        )
        assert response.status_code == 200
        data = response.json()
        
        snapshot_names = [s["name"] for s in data["snapshots"]]
        assert "daily_2025-12-01" in snapshot_names
        assert "daily_2025-11-30" in snapshot_names
        assert "hourly_2025-12-01_14" in snapshot_names
        assert "monthly_2025-11" in snapshot_names
        # system_snapshot_ignored should NOT be listed (no s3root)
        assert "system_snapshot_ignored" not in snapshot_names
        print(f"✓ Snapshots found: {snapshot_names}")

    def test_object_versions_api(self, browser_url, browser_auth):
        """Test API version listing for an object."""
        response = httpx.get(
            f"{browser_url}/api/b/test-bucket/o/documents/document1.txt/versions",
            auth=browser_auth,
        )
        assert response.status_code == 200
        data = response.json()
        
        versions = data["versions"]
        version_ids = [v["version_id"] for v in versions]
        
        # Should have current + 4 snapshots
        assert "current" in version_ids
        assert "daily_2025-12-01" in version_ids
        assert "daily_2025-11-30" in version_ids
        assert "hourly_2025-12-01_14" in version_ids
        assert "monthly_2025-11" in version_ids
        
        # Current should be marked as current
        current = next(v for v in versions if v["version_id"] == "current")
        assert current["is_current"] is True
        assert current["source"] == "current"
        
        # Snapshots should have proper source
        daily = next(v for v in versions if v["version_id"] == "daily_2025-12-01")
        assert daily["source"] == "snapshot"
        assert daily["is_current"] is False
        
        print(f"✓ Found {len(versions)} versions: {version_ids}")

    def test_object_versions_file_not_in_all_snapshots(self, browser_url, browser_auth):
        """Test version listing for a file that doesn't exist in all snapshots."""
        response = httpx.get(
            f"{browser_url}/api/b/test-bucket/o/images/photo.png/versions",
            auth=browser_auth,
        )
        assert response.status_code == 200
        data = response.json()
        
        versions = data["versions"]
        version_ids = [v["version_id"] for v in versions]
        
        # photo.png exists in current and daily_2025-12-01, but NOT in daily_2025-11-30
        assert "current" in version_ids
        assert "daily_2025-12-01" in version_ids
        assert "daily_2025-11-30" not in version_ids
        
        print(f"✓ Partial version history: {version_ids}")

    def test_unauthorized_access(self, browser_url):
        """Test that unauthorized access is rejected."""
        response = httpx.get(f"{browser_url}/api/buckets")
        assert response.status_code == 401
        print("✓ Unauthorized access rejected")

    def test_wrong_credentials(self, browser_url):
        """Test that wrong credentials are rejected."""
        response = httpx.get(
            f"{browser_url}/api/buckets",
            auth=("wronguser", "wrongpass"),
        )
        assert response.status_code == 401
        print("✓ Wrong credentials rejected")


class TestBrowserUI:
    """Test browser HTML UI pages."""

    def test_buckets_page(self, browser_url, browser_auth):
        """Test buckets HTML page."""
        response = httpx.get(
            f"{browser_url}/buckets",
            auth=browser_auth,
        )
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "test-bucket" in response.text
        assert "backup-bucket" in response.text
        print("✓ Buckets page renders correctly")

    def test_objects_page(self, browser_url, browser_auth):
        """Test objects HTML page."""
        response = httpx.get(
            f"{browser_url}/b/test-bucket",
            auth=browser_auth,
        )
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "documents" in response.text
        assert "images" in response.text
        print("✓ Objects page renders correctly")

    def test_object_detail_page(self, browser_url, browser_auth):
        """Test object detail HTML page with versions."""
        response = httpx.get(
            f"{browser_url}/b/test-bucket/o/documents/document1.txt",
            auth=browser_auth,
        )
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "document1.txt" in response.text
        assert "Version History" in response.text
        # Should show snapshots
        assert "daily_2025-12-01" in response.text
        print("✓ Object detail page renders with version history")

    def test_breadcrumb_navigation(self, browser_url, browser_auth):
        """Test breadcrumb navigation is present."""
        response = httpx.get(
            f"{browser_url}/b/test-bucket",
            params={"prefix": "documents/"},
            auth=browser_auth,
        )
        assert response.status_code == 200
        assert "Buckets" in response.text  # Root breadcrumb
        assert "test-bucket" in response.text  # Bucket breadcrumb
        print("✓ Breadcrumb navigation present")
