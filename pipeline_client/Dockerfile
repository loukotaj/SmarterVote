FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome for Selenium
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY pipeline/requirements.txt /tmp/pipeline_requirements.txt
COPY pipeline_client/backend/requirements.txt /tmp/pipeline_client_requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /tmp/pipeline_requirements.txt \
    && pip install --no-cache-dir -r /tmp/pipeline_client_requirements.txt

# Download spaCy model
RUN python -m spacy download en_core_web_sm

# Copy application code
COPY pipeline/app ./pipeline/app
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
