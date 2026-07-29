FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY gree_climate_bridge.py /app/gree_climate_bridge.py

ENV PYTHONUNBUFFERED=1

CMD ["python", "gree_climate_bridge.py"]
