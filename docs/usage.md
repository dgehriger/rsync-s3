# Usage Guide

This guide explains how to use the Rsync.net S3 Gateway and Snapshot-Aware Browser.

## Web Browser Interface

### Accessing the UI

1. Open [http://localhost:8080](http://localhost:8080) in your web browser
2. Enter your credentials (configured in `.env`)
3. You'll see the bucket listing page

### Browsing Buckets

The home page displays all S3 buckets (directories under `~/s3root`):

- Click a bucket name to view its contents
- Buckets show creation date when available

### Browsing Objects

Inside a bucket, you'll see:

- **Folders**: Click to navigate into subdirectories
- **Files**: Shows name, size, and last modified date
- **Actions**: "Details" for version history, "Download" for quick download

Use the breadcrumb navigation at the top to go back to parent folders.

### Viewing Version History

Click "Details" on any file to see:

- **Metadata**: Full path, size, content type, ETag
- **Version History**: All available versions from ZFS snapshots

Each version shows:

- Version identifier (snapshot name or "current")
- Source (S3 Live or Snapshot)
- File size
- Modification timestamp
- Download button

### Downloading Files

You can download:

- **Current version**: Click "Download" in object list or "Download Current" in details
- **Historical version**: Click "Download" next to any version in the history table

## S3 API Access

### Endpoint Configuration

- **Endpoint URL**: `http://localhost:9000`
- **Access Key**: Your configured `S3_ACCESS_KEY`
- **Secret Key**: Your configured `S3_SECRET_KEY`
- **Region**: Any value works (e.g., `us-east-1`)

### AWS CLI Examples

Configure credentials:

```bash
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_ENDPOINT_URL=http://localhost:9000
```

Common operations:

```bash
# List all buckets
aws s3 ls

# List bucket contents
aws s3 ls s3://my-bucket/

# List with recursive
aws s3 ls s3://my-bucket/ --recursive

# Upload a file
aws s3 cp myfile.txt s3://my-bucket/

# Upload a directory
aws s3 sync ./local-folder s3://my-bucket/folder/

# Download a file
aws s3 cp s3://my-bucket/file.txt ./

# Download a directory
aws s3 sync s3://my-bucket/folder/ ./local-folder/

# Delete a file
aws s3 rm s3://my-bucket/file.txt

# Create a bucket (directory)
aws s3 mb s3://new-bucket
```

### Rclone Examples

Configure remote:

```bash
rclone config create rsync-s3 s3 \
    provider=Other \
    endpoint=http://localhost:9000 \
    access_key_id=your-access-key \
    secret_access_key=your-secret-key
```

Usage:

```bash
# List buckets
rclone lsd rsync-s3:

# List files
rclone ls rsync-s3:my-bucket

# Copy files
rclone copy ./local rsync-s3:my-bucket/folder

# Sync directories
rclone sync ./local rsync-s3:my-bucket --progress
```

## Backup Tool Integration

### Restic

```bash
# Set environment
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export RESTIC_REPOSITORY=s3:http://localhost:9000/restic-repo
export RESTIC_PASSWORD=your-restic-password

# Initialize repository
restic init

# Backup
restic backup /path/to/data

# List snapshots
restic snapshots

# Restore
restic restore latest --target /restore/path
```

### Kopia

```bash
# Create repository
kopia repository create s3 \
    --bucket=kopia-repo \
    --endpoint=localhost:9000 \
    --access-key=your-access-key \
    --secret-access-key=your-secret-key \
    --disable-tls

# Create snapshot
kopia snapshot create /path/to/data

# List snapshots
kopia snapshot list

# Restore
kopia restore <snapshot-id> /restore/path
```

### Duplicati

Configure in Duplicati's web interface:

1. Storage Type: S3 Compatible
2. Server: `localhost:9000`
3. Bucket: Your bucket name
4. AWS Access ID: Your access key
5. AWS Secret Key: Your secret key
6. Use SSL: No (for local)

## JSON API

The browser also provides a JSON API for programmatic access:

### List Buckets

```bash
curl -u admin:password http://localhost:8080/api/buckets
```

Response:

```json
{
  "buckets": [
    {"name": "bucket-a", "creation_date": "2025-12-01T00:00:00"},
    {"name": "bucket-b", "creation_date": "2025-11-15T00:00:00"}
  ]
}
```

### List Objects

```bash
curl -u admin:password "http://localhost:8080/api/b/bucket-a?prefix=folder/"
```

Response:

```json
{
  "folders": [
    {"name": "subfolder", "prefix": "folder/subfolder/", "type": "folder"}
  ],
  "files": [
    {"name": "file.txt", "key": "folder/file.txt", "size": 1024, ...}
  ],
  "is_truncated": false,
  "prefix": "folder/"
}
```

### Get Object Versions

```bash
curl -u admin:password http://localhost:8080/api/b/bucket-a/o/folder/file.txt/versions
```

Response:

```json
{
  "versions": [
    {
      "version_id": "current",
      "source": "current",
      "size": 1024,
      "modified_time": "2025-12-02T10:30:00",
      "is_current": true
    },
    {
      "version_id": "daily_2025-12-01",
      "source": "snapshot",
      "size": 1000,
      "modified_time": "2025-12-01T00:00:00",
      "is_current": false
    }
  ]
}
```

### List Snapshots

```bash
curl -u admin:password http://localhost:8080/api/snapshots
```

Response:

```json
{
  "snapshots": [
    {"name": "daily_2025-12-01", "timestamp": "2025-12-01T00:00:00"},
    {"name": "daily_2025-11-30", "timestamp": "2025-11-30T00:00:00"}
  ]
}
```

## Understanding Snapshots

### What Are ZFS Snapshots?

Rsync.net uses ZFS filesystem with automatic snapshots. These are:

- **Point-in-time copies** of your entire filesystem
- **Immutable** - cannot be modified or deleted by users
- **Space-efficient** - only store changes (copy-on-write)
- **Automatic** - created on schedule by rsync.net

### Snapshot Naming Conventions

Rsync.net typically creates snapshots with names like:

- `daily_YYYY-MM-DD` - Daily snapshots
- `hourly_YYYY-MM-DD_HH` - Hourly snapshots
- `monthly_YYYY-MM` - Monthly snapshots

### Accessing Snapshots

Snapshots are exposed under the `.zfs` hidden directory:

```bash
# Via SSH
ssh user@host "ls -la .zfs"
ssh user@host "ls -la .zfs/daily_2025-12-01/s3root/my-bucket/"
```

The browser automates this access, scanning all snapshots to build version history.

### Snapshot Limitations

- You cannot modify or delete snapshots
- Snapshot schedule is controlled by rsync.net
- Very old snapshots may be automatically removed
- Snapshots don't exist for newly created files
