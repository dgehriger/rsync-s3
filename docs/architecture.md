# Architecture

This document describes the architecture of the Rsync.net S3 Gateway with Snapshot-Aware Browser.

## Overview

The system consists of three main components:

```
┌─────────────────────────────────────────────────────────────────┐
│                        Your Network                              │
│                                                                  │
│  ┌─────────────┐    ┌─────────────────┐    ┌─────────────────┐  │
│  │  S3 Clients │    │  Browser (UI)   │    │  Backup Tools   │  │
│  │ (aws-cli)   │    │  FastAPI/Jinja  │    │ (restic, kopia) │  │
│  └──────┬──────┘    └────────┬────────┘    └────────┬────────┘  │
│         │                    │                      │            │
│         │    S3 API (HTTP)   │    HTTP + SFTP       │            │
│         ▼                    ▼                      ▼            │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              Docker Compose Stack                            ││
│  │                                                              ││
│  │  ┌──────────────────┐    ┌───────────────────────────────┐  ││
│  │  │   S3 Gateway     │    │        Browser App            │  ││
│  │  │ (rclone serve)   │◄───│     (FastAPI + Jinja2)        │  ││
│  │  │    Port 9000     │    │         Port 8080             │  ││
│  │  └────────┬─────────┘    └─────────────┬─────────────────┘  ││
│  │           │                            │                    ││
│  │           │  SFTP                      │  SFTP              ││
│  │           │                            │                    ││
│  └───────────┼────────────────────────────┼────────────────────┘│
│              │                            │                      │
└──────────────┼────────────────────────────┼──────────────────────┘
               │                            │
               ▼                            ▼
        ┌─────────────────────────────────────────┐
        │           Rsync.net Server              │
        │                                         │
        │  ~/s3root/                              │
        │    ├── bucket-a/                        │
        │    │     └── files...                   │
        │    └── bucket-b/                        │
        │          └── files...                   │
        │                                         │
        │  ~/.zfs/                                │
        │    ├── daily_2025-12-01/                │
        │    │     └── s3root/...                 │
        │    ├── daily_2025-11-30/                │
        │    │     └── s3root/...                 │
        │    └── ...                              │
        └─────────────────────────────────────────┘
```

## Components

### 1. S3 Gateway (rclone serve s3)

The S3 gateway uses rclone to expose rsync.net storage as an S3-compatible endpoint.

**Responsibilities:**

- Accept S3 API requests on port 9000
- Translate S3 operations to SFTP operations
- Handle authentication using S3 access/secret keys
- Serve directories under `~/s3root` as S3 buckets

**Configuration:**

- Uses rclone's SFTP remote type
- Connects to rsync.net using SSH key authentication
- Environment-based configuration (no config file needed)

**Limitations:**

- No S3 versioning support (single version per object)
- No multipart upload optimization
- Performance limited by SFTP overhead

### 2. Browser Application (FastAPI)

A Python web application providing a user-friendly interface for browsing storage.

**Responsibilities:**

- Web UI for browsing buckets and objects
- Discovery of historical versions from ZFS snapshots
- Streaming downloads from both S3 and SFTP
- User authentication (HTTP Basic Auth)

**Key Modules:**

| Module | Purpose |
|--------|---------|
| `config.py` | Pydantic settings management |
| `s3_client.py` | Async S3 client (aioboto3) |
| `sftp_client.py` | Async SFTP client (asyncssh) |
| `version_mapper.py` | Combines S3 + snapshot versions |
| `main.py` | FastAPI routes and templates |

**API Endpoints:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/buckets` | GET | List all buckets (HTML) |
| `/b/{bucket}` | GET | List objects in bucket (HTML) |
| `/b/{bucket}/o/{path}` | GET | Object details + versions (HTML) |
| `/b/{bucket}/o/{path}/download` | GET | Download object |
| `/api/*` | GET | JSON API equivalents |

### 3. Rsync.net Storage

The remote storage backend provided by rsync.net.

**Directory Structure:**

```
~/                              # User home directory
├── s3root/                     # S3 bucket root (configurable)
│   ├── bucket-a/               # Bucket "bucket-a"
│   │   ├── folder/
│   │   │   └── file.txt
│   │   └── document.pdf
│   └── bucket-b/               # Bucket "bucket-b"
│       └── ...
│
└── .zfs/                       # ZFS snapshot directory (hidden)
    ├── daily_2025-12-01/       # Snapshot from Dec 1
    │   └── s3root/
    │       └── bucket-a/
    │           └── folder/
    │               └── file.txt    # Historical version
    ├── daily_2025-11-30/       # Snapshot from Nov 30
    │   └── ...
    └── monthly_2025-11/        # Monthly snapshot
        └── ...
```

**ZFS Snapshots:**

- Created automatically by rsync.net
- Immutable point-in-time copies
- Accessible via `.zfs` hidden directory
- Naming patterns vary (daily, hourly, monthly)

## Data Flow

### Reading Current Object

```
Client → S3 Gateway → SFTP → rsync.net → ~/s3root/bucket/object
```

### Reading Historical Version

```
Browser → SFTP → rsync.net → ~/.zfs/snapshot/s3root/bucket/object
```

### Version Discovery

```
1. Browser fetches current metadata from S3 Gateway
2. Browser lists snapshots via SFTP (ls ~/.zfs/)
3. For each snapshot, checks if object exists
4. Collects version info (size, timestamp)
5. Presents unified version history in UI
```

## Version Mapping Logic

The version mapper combines current and historical versions:

```python
async def list_object_versions(bucket, key):
    versions = []
    
    # Get current version from S3
    current = await s3_client.head_object(bucket, key)
    if current:
        versions.append(VersionInfo(
            version_id="current",
            source="s3",
            is_current=True,
            ...
        ))
    
    # Get snapshots from SFTP
    snapshots = await sftp_client.list_snapshots()
    
    # Check each snapshot for this object
    for snapshot in snapshots:
        file_info = await sftp_client.stat_snapshot_object(
            snapshot.name, bucket, key
        )
        if file_info:
            versions.append(VersionInfo(
                version_id=snapshot.name,
                source="snapshot",
                ...
            ))
    
    return sorted(versions, by=timestamp, descending=True)
```

## Security Considerations

### Authentication

- S3 Gateway: Access/Secret key authentication
- Browser UI: HTTP Basic Auth over HTTPS (in production)

### Network Security

- Both services run in isolated Docker network
- External access only via mapped ports
- Recommend using reverse proxy with TLS for production

### Secret Management

- SSH key stored in `secrets/` directory
- Credentials in `.env` file (not committed to git)
- Docker volumes mount secrets as read-only

## Scalability

### Current Design

- Single S3 gateway instance
- Single browser instance
- Suitable for individual or small team use

### Potential Improvements

- Multiple rclone instances behind load balancer
- Redis caching for snapshot listings
- Async job queue for large operations
