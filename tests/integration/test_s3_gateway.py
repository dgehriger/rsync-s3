"""
Integration tests for S3 Gateway functionality
"""

import pytest
from botocore.exceptions import ClientError


class TestS3Gateway:
    """Test S3 gateway operations against mock rsync.net."""

    def test_list_buckets(self, s3_client):
        """Test that buckets are listed correctly."""
        response = s3_client.list_buckets()
        bucket_names = [b["Name"] for b in response["Buckets"]]
        
        assert "test-bucket" in bucket_names
        assert "backup-bucket" in bucket_names
        assert "empty-bucket" in bucket_names
        print(f"✓ Found {len(bucket_names)} buckets: {bucket_names}")

    def test_list_objects_in_bucket(self, s3_client):
        """Test listing objects in a bucket."""
        response = s3_client.list_objects_v2(
            Bucket="test-bucket",
            Delimiter="/",
        )
        
        # Check for folders (CommonPrefixes)
        prefixes = [p["Prefix"] for p in response.get("CommonPrefixes", [])]
        assert "documents/" in prefixes
        assert "images/" in prefixes
        print(f"✓ Found folders: {prefixes}")

    def test_list_objects_with_prefix(self, s3_client):
        """Test listing objects with a prefix (folder contents)."""
        response = s3_client.list_objects_v2(
            Bucket="test-bucket",
            Prefix="documents/",
        )
        
        keys = [obj["Key"] for obj in response.get("Contents", [])]
        assert "documents/document1.txt" in keys
        assert "documents/report.txt" in keys
        print(f"✓ Found files in documents/: {keys}")

    def test_get_object(self, s3_client):
        """Test downloading an object."""
        response = s3_client.get_object(
            Bucket="test-bucket",
            Key="documents/document1.txt",
        )
        
        content = response["Body"].read().decode("utf-8")
        assert "CURRENT version" in content
        print(f"✓ Downloaded document1.txt: '{content.strip()}'")

    def test_head_object(self, s3_client):
        """Test getting object metadata."""
        response = s3_client.head_object(
            Bucket="test-bucket",
            Key="documents/document1.txt",
        )
        
        assert response["ContentLength"] > 0
        assert "LastModified" in response
        print(f"✓ Object metadata: size={response['ContentLength']}, modified={response['LastModified']}")

    def test_put_object(self, s3_client):
        """Test uploading a new object."""
        test_content = b"This is a test file created during integration testing"
        
        s3_client.put_object(
            Bucket="test-bucket",
            Key="test-upload.txt",
            Body=test_content,
        )
        
        # Verify upload
        response = s3_client.get_object(
            Bucket="test-bucket",
            Key="test-upload.txt",
        )
        downloaded = response["Body"].read()
        assert downloaded == test_content
        
        # Cleanup
        s3_client.delete_object(
            Bucket="test-bucket",
            Key="test-upload.txt",
        )
        print("✓ Upload and delete successful")

    def test_empty_bucket(self, s3_client):
        """Test that empty bucket lists correctly."""
        response = s3_client.list_objects_v2(Bucket="empty-bucket")
        
        assert response.get("KeyCount", 0) == 0
        assert "Contents" not in response or len(response["Contents"]) == 0
        print("✓ Empty bucket is empty")

    def test_nonexistent_bucket(self, s3_client):
        """Test accessing a nonexistent bucket raises error."""
        with pytest.raises(ClientError) as exc_info:
            s3_client.list_objects_v2(Bucket="nonexistent-bucket-12345")
        
        assert exc_info.value.response["Error"]["Code"] in ["NoSuchBucket", "404"]
        print("✓ Nonexistent bucket raises error")

    def test_nonexistent_object(self, s3_client):
        """Test accessing a nonexistent object raises error."""
        with pytest.raises(ClientError) as exc_info:
            s3_client.get_object(
                Bucket="test-bucket",
                Key="nonexistent-file.txt",
            )
        
        assert exc_info.value.response["Error"]["Code"] in ["NoSuchKey", "404"]
        print("✓ Nonexistent object raises error")
