# Rsync.net S3 Gateway + Snapshot-Aware Browser

## Architecture & Implementation Plan

## 0. Purpose and Summary

Rsync.net provides highly reliable offsite backup storage over SSH/SFTP, along with powerful **ZFS filesystem snapshots** exposed under the hidden path `~/.zfs/`. These snapshots give per-directory, immutable historical versions of the filesystem but are not directly usable by S3-compatible backup tools such as **restic**, **kopia**, **rclone**, **MinIO clients**, or cloud-native S3 tooling.

The goal of this project is to build a **complete, self-hosted S3-compatible storage gateway in front of rsync.net**, combined with a **browser UI** that exposes `.zfs` snapshots as **historical object versions**, enabling:

- Using rsync.net as **S3-compatible storage** for backup tools
- Browsing buckets, objects, and historical versions through a web UI
- Downloading any past version directly from rsync.net
- Running everything in a lightweight **Docker Compose** stack
- Zero modification of rsync.net account; uses only standard SFTP access

This stack simulates versioning for humans (UI-level versioning) but **does not attempt to re-implement S3 API versioning**, because rsync.net snapshots do not follow S3 semantics. All S3 clients see a normal, non-versioned S3 endpoint.

---

## 1. Architecture

### 1.1 High-Level Components

#### 1. S3 Gateway

- Implemented using: `rclone serve s3 rsyncnet:s3root`
- Backend: rclone SFTP remote to rsync.net
- Behavior:
  - Each directory under `~/s3root` becomes an S3 bucket
  - Files inside buckets are exposed as S3 objects
  - No S3 versioning support (standard rclone behavior)

#### 2. Snapshot-Aware Browser

- Implemented using Python FastAPI (or equivalent)
- Connects to two backends:
  - **S3** → talking to the rclone gateway
  - **SFTP** → directly reading rsync.net `.zfs` snapshots
- Provides:
  - Bucket and object listing (via S3)
  - Discovery of historical versions (by scanning `~/.zfs/*/s3root/...`)
  - Download of any historical version (via SFTP streaming)
  - Clean, web-friendly UI with breadcrumbs

#### 3. (Optional) Reverse Proxy

- nginx / Caddy / Traefik
- Handles:
  - TLS termination
  - Authentication for the web UI
  - Optionally protect S3 endpoint

---

### 1.2 Data Layout on Rsync.net

#### Live Data

```text
~/s3root/
    bucket-a/
        foo/bar/file1.txt
    bucket-b/
        ...
```

#### Snapshots

```text
~/.zfs/daily_2025-12-01/
    s3root/
        bucket-a/foo/bar/file1.txt
~/.zfs/daily_2025-11-30/
    s3root/
        bucket-a/foo/bar/file1.txt
~/.zfs/custom_monthly_2025-12-01/
    ...
```

#### Version Mapping

For S3 bucket `bucket-a`, key `foo/bar/file1.txt`:

| Version ID         | Source       | Path                                                        | How Downloaded |
| ------------------ | ------------ | ----------------------------------------------------------- | -------------- |
| `current`          | Live S3      | `~/s3root/bucket-a/foo/bar/file1.txt`                       | via S3         |
| `daily_2025-12-01` | ZFS snapshot | `~/.zfs/daily_2025-12-01/s3root/bucket-a/foo/bar/file1.txt` | via SFTP       |
| …                  | …            | …                                                           | …              |

---

## 2. Data Flow

### S3 Clients (restic, kopia, aws-cli, etc.)

→ HTTP → **rclone serve s3** → SFTP → **rsync.net**

### Web UI

- Bucket/Object listing via S3 client (boto3)
- Version discovery + version download via SFTP client

Separate responsibilities:

- S3 for **current** view
- SFTP for **historical versions**

---

## 3. Deployment Topology (Docker Compose)

```text
+-------------------------------+
|         Browser (FastAPI)     |
|        http://host:8080       |
+-------------------------------+
               |
               | S3 (HTTP)
               v
+-------------------------------+
|       rclone S3 Gateway       |
|       http://host:9000        |
+-------------------------------+
               |
               | SFTP (SSH)
               v
+-------------------------------+
|         rsync.net server      |
|    with ZFS + .zfs snapshots  |
+-------------------------------+
```

Optional:

```text
Reverse Proxy (TLS/auth)
     /ui  → Browser
     /s3  → rclone serve s3
```

---

## 4. Implementation Plan (with Checkboxes)

### 4.1 Preparation

1. [x] Decide on final ports, TLS, auth strategy
2. [x] Generate SSH key for rsync.net and store in `./secrets/`
3. [x] Set up `.env` with:
   - [x] `RSYNC_HOST`
   - [x] `RSYNC_USER`
   - [x] `S3_ACCESS_KEY`, `S3_SECRET_KEY`

---

### 4.2 Project Structure

1. [x] Create repo folders:
   - [x] `docker-compose.yml`
   - [x] `/browser/app/`
   - [x] `/browser/Dockerfile`
   - [x] `/config/`
   - [x] `/docs/`

2. [x] Add `README.md` describing project goals and architecture (based on this document)

---

### 4.3 rclone S3 Gateway

1. [x] Configure Rclone SFTP remote (environment variables)
2. [x] Create `/secrets/rsync_id_ed25519` volume
3. [x] Add Docker compose service:
   - [x] Image `rclone/rclone`
   - [x] Command `serve s3 rsyncnet:s3root`
   - [x] Environment with rclone config
   - [x] Port `9000:9000`
4. [ ] Confirm buckets appear using `aws s3 ls --endpoint-url=http://localhost:9000`

---

### 4.4 Browser Application – Configuration

1. [x] Implement `Settings` (Pydantic) containing:
    - S3 endpoint/creds
    - rsync.net host/user/key path
    - snapshot directory `.zfs`
    - S3 root prefix (`s3root`)

---

### 4.5 Browser Application – S3 Integration

1. [x] Add boto3/aioboto3 client
2. [x] Implement:
    - [x] `list_buckets()`
    - [x] `list_objects(bucket, prefix)`
    - [x] `head_object(bucket, key)`
    - [x] Streaming `get_object_content(bucket, key)`

---

### 4.6 Browser Application – SFTP Integration

1. [x] Add `asyncssh` dependency
2. [x] Implement SFTP connectivity:
    - [x] One-shot SFTP connect helper
    - [x] `list_snapshots()` = list directories under `.zfs`
    - [x] `snapshot_root(snap)` = `.zfs/<snap>/s3root`
    - [x] `stat_snapshot_object()`
    - [x] `open_snapshot_file_stream()`

---

### 4.7 Browser Application – Version Mapping

1. [x] Create `VersionInfo` class
2. [x] Implement `list_object_versions(bucket, key)`:
    - [x] Add current version (via S3 head)
    - [x] For each snapshot:
      - [x] Check existence via SFTP
      - [x] Collect snapshot metadata
3. [x] Ensure versions are sorted by timestamp descending
4. [x] Write unit tests for version mapping logic

---

### 4.8 Browser Application – HTTP API

1. [x] `GET /buckets`
2. [x] `GET /b/{bucket}`
3. [x] `GET /b/{bucket}/o/{path:path}`
4. [x] `GET /b/{bucket}/o/{path:path}/download` for current
5. [x] `GET /b/{bucket}/o/{path:path}/download?version={snap}` for snapshot

---

### 4.9 Browser Application – UI

1. [x] Add Jinja2 templates:
    - [x] `buckets.html`
    - [x] `objects.html`
    - [x] `object_detail.html`
2. [x] Implement breadcrumb navigation
3. [x] Add version history table with download links
4. [x] Add CSS styling

---

### 4.10 Browser Application – Dockerization

1. [x] `browser/Dockerfile` with Uvicorn entrypoint
2. [x] Add service in `docker-compose.yml`:
    - [x] Ports `8080:8080`
    - [x] Environment mapping to Settings
    - [x] Mount ssh key
3. [ ] Confirm UI loads and can list buckets

---

### 4.11 Authentication & Security

1. [x] Implement Basic Auth in FastAPI OR
2. [x] Add reverse proxy with:
    - [x] TLS
    - [x] Auth
    - [x] Rate limiting (optional)
3. [x] Optionally restrict rclone gateway to LAN-only

---

### 4.12 Logging & Observability

1. [x] Add structured logging in FastAPI
2. [x] Add error handlers
3. [ ] Expose simple metrics (optional)

---

### 4.13 Testing

#### Unit

1. [x] Version mapping logic
2. [x] Snapshot path resolution

#### Integration

1. [x] Mock SFTP server container mimicking rsync.net
2. [x] Start rclone gateway in compose
3. [x] Browser connects to mock S3 + mock SFTP
4. [x] End-to-end object + version listing tests

---

### 4.14 Validation With Real Rsync.net

1. [ ] Upload sample files
2. [ ] Wait for auto snapshots
3. [ ] Verify `.zfs` structure
4. [ ] Validate UI version view
5. [ ] Validate SFTP version download
6. [ ] Confirm integrity with checksums

---

### 4.15 Production Deployment

1. [ ] Deploy on target host
2. [x] Configure reverse proxy (TLS + auth)
3. [ ] Lock down firewall rules
4. [x] Enable automated restarts
5. [ ] Configure monitoring/alerts

---

### 4.16 Documentation

1. [x] Write:
    - [x] `docs/setup.md`
    - [x] `docs/architecture.md`
    - [x] `docs/usage.md`
2. [x] Add diagrams
3. [x] Describe assumptions and limitations

---

### 4.17 Optional Enhancements

1. [ ] "Restore version" button (snapshot → upload back to S3)
2. [x] JSON API for versions
3. [ ] Snapshot diffing (size/time)
4. [ ] Support for multiple rsync.net accounts
5. [ ] Indexing + search

