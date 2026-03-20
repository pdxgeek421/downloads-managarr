FROM python:3.12-slim

# Install gosu for privilege dropping (same pattern as linuxserver.io)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

# Create a placeholder appuser/appgroup (will be remapped at runtime via PUID/PGID)
RUN groupadd -g 1000 appuser \
    && useradd -u 1000 -g appuser -s /bin/sh -M appuser

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Copy entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Config/queue volume mount point
RUN mkdir -p /config && chown appuser:appuser /config

# Expose default port (override with DOWNLOADS_MANAGARR_PORT)
EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
# Port is resolved from DOWNLOADS_MANAGARR_PORT in entrypoint.sh
CMD []
