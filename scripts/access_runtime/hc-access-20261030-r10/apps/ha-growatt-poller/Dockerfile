FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY ha_growatt_poller.py /app/ha_growatt_poller.py

ENV PYTHONUNBUFFERED=1

CMD ["python", "ha_growatt_poller.py"]
