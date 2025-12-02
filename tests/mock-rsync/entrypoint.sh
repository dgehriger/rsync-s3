#!/bin/bash
set -e

# Setup SSH authorized keys from environment or mounted file
if [ -f /secrets/authorized_keys ]; then
    cp /secrets/authorized_keys /home/testuser/.ssh/authorized_keys
    chmod 600 /home/testuser/.ssh/authorized_keys
    chown testuser:testuser /home/testuser/.ssh/authorized_keys
fi

# Initialize test data (s3root and .zfs snapshots)
/init-data.sh

# Fix permissions
chown -R testuser:testuser /home/testuser

# Start SSH daemon
echo "Starting SSH server..."
exec /usr/sbin/sshd -D -e
