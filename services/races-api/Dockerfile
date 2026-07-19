FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

WORKDIR /app

COPY requirements-constraints.txt .
COPY services/races-api/requirements.txt .
RUN pip install --no-cache-dir -c requirements-constraints.txt -r requirements.txt

COPY services/races-api/main.py .
COPY services/races-api/config.py .
COPY services/races-api/constants.py .
COPY services/races-api/schemas.py .
COPY services/races-api/simple_publish_service.py .
COPY services/races-api/analytics_middleware.py .
COPY services/races-api/analytics_store.py .
COPY services/races-api/cloudflare_analytics.py .
COPY services/races-api/chamber_narratives.py .
COPY services/races-api/auth.py .
COPY services/races-api/request_models.py .
COPY services/races-api/firestore_helpers.py .
COPY services/races-api/gcs_helpers.py .
COPY services/races-api/cloud_run_jobs.py .
COPY services/races-api/rate_limit.py .
COPY services/races-api/routers ./routers
COPY shared /app/shared
# data/published is NOT baked into the image — deployed instances read from GCS.
# For local dev, mount or copy data/published manually.
RUN mkdir -p /app/data/published

RUN useradd --create-home --shell /usr/sbin/nologin app \
    && chown -R app:app /app
USER app

ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data/published/

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
