FROM python@sha256:6c4dd321d176d61ea848dc8c73a4f7dbae8f70e0ee48bb411ea2f045b599fa8e

WORKDIR /app

COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir -r /app/requirements.lock

COPY ha_growatt_poller.py /app/ha_growatt_poller.py
COPY mqtt_credentials.py worker_health.py /app/
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 CMD ["python", "worker_health.py", "--mode", "live"]

ENV PYTHONUNBUFFERED=1

CMD ["python", "ha_growatt_poller.py"]
