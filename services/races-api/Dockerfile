FROM python:3.10-slim

WORKDIR /app

COPY services/races-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/races-api/main.py .
COPY services/races-api/config.py .
COPY services/races-api/constants.py .
COPY services/races-api/schemas.py .
COPY services/races-api/simple_publish_service.py .
COPY shared /app/shared
# data/published is NOT baked into the image — deployed instances read from GCS.
# For local dev, mount or copy data/published manually.
RUN mkdir -p /app/data/published

ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data/published/

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
