#!/bin/sh
set -e

# Write SSH key from base64-encoded environment variable if provided
if [ -n "$SSH_PRIVATE_KEY_B64" ]; then
    echo "$SSH_PRIVATE_KEY_B64" | base64 -d > /secrets/rsync_id_ed25519
    chmod 600 /secrets/rsync_id_ed25519
    echo "SSH key written to /secrets/rsync_id_ed25519"
fi

# Execute the main command
exec "$@"
