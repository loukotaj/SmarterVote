FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY pipeline_client/backend/requirements.txt /tmp/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy application code
COPY pipeline_v2 ./pipeline_v2
COPY pipeline/app/utils ./pipeline/app/utils
COPY pipeline/app/__init__.py ./pipeline/app/__init__.py
COPY shared ./shared

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import pipeline_v2; print('Pipeline V2 ready')" || exit 1

# Default command (override in Cloud Run Job)
ENTRYPOINT ["python", "-m", "pipeline_v2"]
