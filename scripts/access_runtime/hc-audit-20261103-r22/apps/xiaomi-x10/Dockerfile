ARG PYTHON_BASE_IMAGE
FROM ${PYTHON_BASE_IMAGE}

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY . .
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 CMD ["python", "worker_health.py", "--mode", "live"]

CMD ["python", "xiaomi_x10_bridge.py"]
