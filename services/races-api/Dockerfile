FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY ../../pipeline /app/pipeline

ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data/published/

EXPOSE 8080

CMD ["python", "main.py"]
