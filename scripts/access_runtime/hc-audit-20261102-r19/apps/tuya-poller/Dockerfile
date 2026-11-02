ARG PYTHON_BASE_IMAGE
FROM ${PYTHON_BASE_IMAGE}

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY tuya_poller.py .
COPY command_dispatcher.py mqtt_credentials.py telemetry_publish.py worker_health.py ./
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 CMD ["python", "worker_health.py", "--mode", "live"]

CMD ["python", "-u", "/app/tuya_poller.py"]
