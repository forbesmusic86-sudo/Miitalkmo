# Multi-stage build for Miitalkmo Nuance Vocalizer TTS API

########## Build Environment ##########
FROM python:3.10.16-alpine3.21 AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apk update && apk add --no-cache \
    build-base \
    gcc \
    g++ \
    make \
    cmake \
    git \
    openssl-dev \
    libffi-dev

WORKDIR /build

# Copy requirements
COPY requirements.txt .

# Build Python dependencies wheel
RUN pip install --upgrade pip setuptools wheel && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -r requirements.txt


########## Runtime Environment ##########
FROM python:3.10.16-alpine3.21

# Install runtime dependencies
RUN apk update && apk add --no-cache \
    libstdc++ \
    libgcc \
    ffmpeg \
    curl \
    ca-certificates

# Create application directory
RUN mkdir -p /app /tmp/tts_cache /tmp/user/config
WORKDIR /app

# Copy wheels from builder
COPY --from=builder /build/wheels /wheels

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache /wheels/* && \
    pip install gunicorn --no-cache-dir

# Copy application code
COPY api/*.py ./
COPY config/ ./config/

# Create non-root user for security
RUN addgroup -g 1000 ttsapi && \
    adduser -D -u 1000 -G ttsapi ttsapi && \
    chown -R ttsapi:ttsapi /app /tmp/tts_cache

USER ttsapi

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Expose port
EXPOSE 5000

# Run with gunicorn
ENTRYPOINT ["gunicorn", \
    "-b", "0.0.0.0:5000", \
    "-w", "4", \
    "-k", "uvicorn.workers.UvicornWorker", \
    "-t", "120", \
    "--access-logfile", "-", \
    "--error-logfile", "-", \
    "main:app"]
