# Mock rsync.net server with simulated ZFS snapshots
# This container provides SSH/SFTP access with a .zfs directory structure

FROM alpine:3.19

# Install OpenSSH server
RUN apk add --no-cache \
    openssh \
    openssh-sftp-server \
    bash \
    && mkdir -p /var/run/sshd

# Create test user (simulating rsync.net user)
RUN adduser -D -s /bin/bash testuser \
    && echo "testuser:testpass" | chpasswd \
    && mkdir -p /home/testuser/.ssh \
    && chmod 700 /home/testuser/.ssh

# SSH configuration for key-based auth
RUN ssh-keygen -A

# Configure SSH
RUN echo "PermitRootLogin no" >> /etc/ssh/sshd_config \
    && echo "PasswordAuthentication no" >> /etc/ssh/sshd_config \
    && echo "PubkeyAuthentication yes" >> /etc/ssh/sshd_config \
    && echo "Subsystem sftp /usr/lib/ssh/sftp-server" >> /etc/ssh/sshd_config \
    && echo "AllowUsers testuser" >> /etc/ssh/sshd_config

# Copy initialization script
COPY init-data.sh /init-data.sh
RUN chmod +x /init-data.sh

# Copy entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 22

ENTRYPOINT ["/entrypoint.sh"]
