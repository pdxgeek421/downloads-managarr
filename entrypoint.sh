#!/bin/bash
set -e

PUID=${PUID:-1000}
PGID=${PGID:-1000}

echo "Downloads-Managarr starting with UID=${PUID} GID=${PGID}"

# Create group if it doesn't exist with the requested GID
if ! getent group appuser >/dev/null 2>&1; then
    groupadd -g "${PGID}" appuser
else
    groupmod -o -g "${PGID}" appuser
fi

# Create user if it doesn't exist with the requested UID
if ! getent passwd appuser >/dev/null 2>&1; then
    useradd -u "${PUID}" -g appuser -s /bin/sh -M appuser
else
    usermod -o -u "${PUID}" -g appuser appuser
fi

# Ensure /config directory exists and is owned by appuser
mkdir -p /config
chown -R appuser:appuser /config 2>/dev/null || true

# Ensure /app is readable (it should be from the image build)
chown -R appuser:appuser /app 2>/dev/null || true

PORT="${DOWNLOADS_MANAGARR_PORT:-8080}"
echo "Starting server on port ${PORT}"
exec gosu appuser uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
