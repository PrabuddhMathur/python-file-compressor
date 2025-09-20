# Multi-stage Dockerfile for PDF Compressor Flask Application
# Optimized for Google Cloud Run deployment

# Build stage
FROM python:3.11-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies for building
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create and set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Create virtual environment and install Python dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim as production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV FLASK_ENV=production
ENV PORT=8080

# Install system dependencies for runtime
RUN apt-get update && apt-get install -y \
    ghostscript \
    libgs-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

# Set working directory
WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create necessary directories with proper permissions
RUN mkdir -p /app/storage/{uploads,processed,temp} && \
    mkdir -p /app/instance && \
    chown -R appuser:appgroup /app

# Copy application code
COPY --chown=appuser:appgroup . .

# Switch to non-root user
USER appuser

# Verify ghostscript installation
RUN gs --version

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:$PORT/health/live', timeout=10)" || exit 1

# Expose port
EXPOSE $PORT

# Run the application
CMD ["python", "app.py"]
