#!/bin/bash
# Initialize mock rsync.net data with simulated ZFS snapshots

USER_HOME=/home/testuser
S3ROOT=$USER_HOME/s3root
ZFSDIR=$USER_HOME/.zfs

echo "Initializing mock rsync.net data..."

# Create s3root structure (live data)
mkdir -p $S3ROOT/test-bucket/documents
mkdir -p $S3ROOT/test-bucket/images
mkdir -p $S3ROOT/backup-bucket/daily
mkdir -p $S3ROOT/empty-bucket

# Create test files with varying content
echo "This is the CURRENT version of document1.txt" > $S3ROOT/test-bucket/documents/document1.txt
echo "Report data v3 - latest changes applied" > $S3ROOT/test-bucket/documents/report.txt
echo "PNG_IMAGE_DATA_CURRENT" > $S3ROOT/test-bucket/images/photo.png
echo "Current backup file content" > $S3ROOT/backup-bucket/daily/backup-2025-12-02.tar.gz

# Create simulated .zfs snapshot directory
# Note: This is a simulation - real ZFS would have this as a special filesystem
mkdir -p $ZFSDIR

# === Snapshot: daily_2025-12-01 (yesterday) ===
SNAP1=$ZFSDIR/daily_2025-12-01/s3root
mkdir -p $SNAP1/test-bucket/documents
mkdir -p $SNAP1/test-bucket/images
mkdir -p $SNAP1/backup-bucket/daily

echo "This is YESTERDAY's version of document1.txt" > $SNAP1/test-bucket/documents/document1.txt
echo "Report data v2 - from yesterday" > $SNAP1/test-bucket/documents/report.txt
echo "PNG_IMAGE_DATA_V2" > $SNAP1/test-bucket/images/photo.png
# Note: This file existed yesterday with different name
echo "Yesterday's backup" > $SNAP1/backup-bucket/daily/backup-2025-12-01.tar.gz

# Set modification times to simulate yesterday
touch -d "2025-12-01 23:00:00" $SNAP1/test-bucket/documents/document1.txt
touch -d "2025-12-01 22:30:00" $SNAP1/test-bucket/documents/report.txt
touch -d "2025-12-01 20:00:00" $SNAP1/test-bucket/images/photo.png

# === Snapshot: daily_2025-11-30 (2 days ago) ===
SNAP2=$ZFSDIR/daily_2025-11-30/s3root
mkdir -p $SNAP2/test-bucket/documents
mkdir -p $SNAP2/test-bucket/images

echo "This is the ORIGINAL version of document1.txt from Nov 30" > $SNAP2/test-bucket/documents/document1.txt
echo "Report data v1 - original" > $SNAP2/test-bucket/documents/report.txt
# photo.png didn't exist yet

touch -d "2025-11-30 18:00:00" $SNAP2/test-bucket/documents/document1.txt
touch -d "2025-11-30 17:00:00" $SNAP2/test-bucket/documents/report.txt

# === Snapshot: hourly_2025-12-01_14 (yesterday 2pm) ===
SNAP3=$ZFSDIR/hourly_2025-12-01_14/s3root
mkdir -p $SNAP3/test-bucket/documents

echo "Document1 as of yesterday 2pm" > $SNAP3/test-bucket/documents/document1.txt
touch -d "2025-12-01 14:00:00" $SNAP3/test-bucket/documents/document1.txt

# === Snapshot: monthly_2025-11 (monthly snapshot) ===
SNAP4=$ZFSDIR/monthly_2025-11/s3root
mkdir -p $SNAP4/test-bucket/documents

echo "Document1 from monthly snapshot November 2025" > $SNAP4/test-bucket/documents/document1.txt
touch -d "2025-11-01 00:00:00" $SNAP4/test-bucket/documents/document1.txt

# Create a snapshot without s3root (should be ignored by browser)
mkdir -p $ZFSDIR/system_snapshot_ignored

# Set current file timestamps
touch -d "2025-12-02 10:30:00" $S3ROOT/test-bucket/documents/document1.txt
touch -d "2025-12-02 09:00:00" $S3ROOT/test-bucket/documents/report.txt
touch -d "2025-12-02 08:00:00" $S3ROOT/test-bucket/images/photo.png

echo "Mock data initialization complete!"
echo ""
echo "Structure created:"
echo "  s3root/"
echo "    test-bucket/"
echo "      documents/document1.txt, report.txt"
echo "      images/photo.png"
echo "    backup-bucket/"
echo "      daily/backup-2025-12-02.tar.gz"
echo "    empty-bucket/"
echo ""
echo "  .zfs/"
echo "    daily_2025-12-01/"
echo "    daily_2025-11-30/"
echo "    hourly_2025-12-01_14/"
echo "    monthly_2025-11/"
