FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY pipeline_client/backend/requirements.txt /tmp/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && pip install --no-cache-dir python-dotenv

# Copy application code
COPY pipeline_v2 ./pipeline_v2
COPY pipeline_client/backend ./pipeline_client/backend
COPY pipeline_client/run.py ./run.py
COPY shared ./shared

# Create non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8001

# Run the pipeline client
ENTRYPOINT ["python", "run.py"]
