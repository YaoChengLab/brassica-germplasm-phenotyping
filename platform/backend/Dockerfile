# ===============================
# CPU-Optimized Dockerfile
# Multi-stage build for efficient caching
# ===============================

# ===============================
# Stage 1: Builder
# ===============================
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip, setuptools, and wheel
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy requirements and install Python packages to cache directory
COPY requirements.txt .
RUN pip install --cache-dir=/tmp/pip-cache --no-cache-dir --prefer-binary \
    -r requirements.txt

# ===============================
# Stage 2: Runtime
# ===============================
FROM python:3.11-slim

WORKDIR /app

# Install minimal runtime dependencies (no build tools).
# The OpenGL/X11 libraries (libgl1-mesa-dev, libsm6, libxext6, libxrender1,
# libxcb1, libfontconfig1) were opencv/ultralytics requirements and went away
# with the image-analysis page.
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    libglib2.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/data/results /app/data/logs

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]