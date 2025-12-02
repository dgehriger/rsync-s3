# Setup Guide

This guide walks you through setting up the Rsync.net S3 Gateway with Snapshot-Aware Browser.

## Prerequisites

- Docker and Docker Compose installed
- SSH access to your rsync.net account
- SSH key pair for rsync.net authentication

## Quick Start

### 1. Clone the Repository

```bash
git clone <repository-url>
cd rsync-s3
```

### 2. Configure SSH Key

Place your rsync.net SSH private key in the `secrets/` directory:

```bash
# If you have an existing key
cp ~/.ssh/your_rsync_key secrets/rsync_id_ed25519
chmod 600 secrets/rsync_id_ed25519

# Or generate a new key
ssh-keygen -t ed25519 -f secrets/rsync_id_ed25519 -N ""
```

Add the public key to your rsync.net account:

```bash
cat secrets/rsync_id_ed25519.pub | ssh xxxxxx@xxxxxx.rsync.net 'cat >> .ssh/authorized_keys'
```

### 3. Configure Environment

Copy the example environment file and edit it:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```bash
# Rsync.net connection
RSYNC_HOST=xxxxxx.rsync.net
RSYNC_USER=xxxxxx

# S3 Gateway credentials (choose your own)
S3_ACCESS_KEY=your-secure-access-key
S3_SECRET_KEY=your-secure-secret-key

# Browser authentication
AUTH_USERNAME=admin
AUTH_PASSWORD=your-secure-password

# Logging level
LOG_LEVEL=INFO
```

### 4. Create S3 Root Directory

SSH into your rsync.net account and create the S3 root directory:

```bash
ssh xxxxxx@xxxxxx.rsync.net "mkdir -p s3root"
```

Create your first bucket:

```bash
ssh xxxxxx@xxxxxx.rsync.net "mkdir -p s3root/my-first-bucket"
```

### 5. Start the Services

```bash
docker-compose up -d
```

### 6. Verify Everything Works

Check service status:

```bash
docker-compose ps
```

Test the S3 gateway:

```bash
aws s3 ls --endpoint-url=http://localhost:9000 \
    --no-sign-request
```

Open the browser UI at [http://localhost:8080](http://localhost:8080) and log in with your configured credentials.

## Detailed Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `RSYNC_HOST` | Rsync.net hostname | - |
| `RSYNC_USER` | Rsync.net username | - |
| `S3_ACCESS_KEY` | S3 gateway access key | - |
| `S3_SECRET_KEY` | S3 gateway secret key | - |
| `AUTH_USERNAME` | Browser login username | `admin` |
| `AUTH_PASSWORD` | Browser login password | `changeme` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |

### Docker Compose Services

The stack consists of two services:

1. **s3-gateway**: rclone serving rsync.net as S3 (port 9000)
2. **browser**: FastAPI web UI for browsing (port 8080)

### Ports

| Service | Port | Purpose |
|---------|------|---------|
| S3 Gateway | 9000 | S3-compatible API endpoint |
| Browser | 8080 | Web UI |

## Using with Backup Tools

### AWS CLI

```bash
aws configure set aws_access_key_id your-access-key
aws configure set aws_secret_access_key your-secret-key

# List buckets
aws s3 ls --endpoint-url=http://localhost:9000

# Upload files
aws s3 cp myfile.txt s3://my-bucket/ --endpoint-url=http://localhost:9000
```

### Restic

```bash
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export RESTIC_REPOSITORY=s3:http://localhost:9000/restic-repo

restic init
restic backup /path/to/data
```

### Rclone

```bash
rclone config create rsync-s3 s3 \
    provider=Other \
    endpoint=http://localhost:9000 \
    access_key_id=your-access-key \
    secret_access_key=your-secret-key

rclone ls rsync-s3:my-bucket
```

## Troubleshooting

### Cannot connect to rsync.net

1. Verify SSH key permissions: `chmod 600 secrets/rsync_id_ed25519`
2. Test manual SSH: `ssh -i secrets/rsync_id_ed25519 xxxxxx@xxxxxx.rsync.net`
3. Check Docker logs: `docker-compose logs s3-gateway`

### S3 operations fail

1. Verify S3 credentials in `.env`
2. Check if `s3root` directory exists on rsync.net
3. Review gateway logs: `docker-compose logs s3-gateway`

### Browser shows no snapshots

1. Snapshots are created automatically by rsync.net
2. Check if `.zfs` is accessible: `ssh user@host "ls -la .zfs"`
3. Snapshots may take time to appear (check rsync.net schedule)

### Authentication issues

1. Verify `AUTH_USERNAME` and `AUTH_PASSWORD` in `.env`
2. Clear browser cache and cookies
3. Check browser logs: `docker-compose logs browser`
