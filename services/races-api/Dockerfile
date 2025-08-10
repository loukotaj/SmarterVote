FROM python:3.9-slim

WORKDIR /app

COPY services/races-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/races-api/main.py .
COPY services/races-api/simple_publish_service.py .
COPY shared /app/shared

ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data/published/

EXPOSE 8080

CMD ["python", "main.py"]
