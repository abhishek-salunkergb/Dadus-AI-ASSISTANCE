# ==============================================================================
# DADUS - Personal AI Operating Assistant
# Production Dockerfile for Web, API & MCP Cloud Deployment
# ==============================================================================

FROM python:3.10-slim

# Prevent Python from writing .pyc files and enable unbuffered streaming logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    API_HOST=0.0.0.0 \
    API_PORT=8000

WORKDIR /app

# Install minimal OS dependencies for audio compilation, C extensions, and healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    portaudio19-dev \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root user and persistent directories
RUN useradd -m -u 1000 -s /bin/bash appuser && \
    mkdir -p /app/data /app/logs && \
    chown -R appuser:appuser /app

# Install Python dependencies in cached layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application codebase (filtered by .dockerignore)
COPY . .

# Set proper ownership for all copied files
RUN chown -R appuser:appuser /app

# Declare persistent volumes for SQLite database and audit logs
VOLUME ["/app/data", "/app/logs"]

# Switch to unprivileged user
USER appuser

# Expose API & Web UI port
EXPOSE 8000

# Container healthcheck with 10s start period to allow cold-boot initialization
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/api/status || exit 1

# Launch DADUS FastAPI & WebSocket server with proxy header support
CMD ["python", "-m", "uvicorn", "app.api.server:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
