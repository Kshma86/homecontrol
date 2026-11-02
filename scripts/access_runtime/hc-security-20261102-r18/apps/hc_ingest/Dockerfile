ARG INGEST_BASE_IMAGE
FROM ${INGEST_BASE_IMAGE}

WORKDIR /app

COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY mqtt_ingest_multi.py mqtt_flood_detector.py ingest_runtime.py measurement_batch.py ingest_healthcheck.py mqtt_credentials.py ./

HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 CMD ["python", "ingest_healthcheck.py", "--mode", "live"]

CMD ["python", "mqtt_ingest_multi.py"]
