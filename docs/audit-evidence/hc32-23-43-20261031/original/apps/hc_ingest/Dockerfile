ARG INGEST_BASE_IMAGE=python:3.11-slim
FROM ${INGEST_BASE_IMAGE}

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mqtt_ingest_multi.py mqtt_flood_detector.py ingest_runtime.py measurement_batch.py ingest_healthcheck.py mqtt_credentials.py ./

HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 CMD ["python", "ingest_healthcheck.py", "--mode", "live"]

CMD ["python", "mqtt_ingest_multi.py"]
