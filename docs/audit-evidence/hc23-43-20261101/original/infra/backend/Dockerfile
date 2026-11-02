FROM python@sha256:6c4dd321d176d61ea848dc8c73a4f7dbae8f70e0ee48bb411ea2f045b599fa8e

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client rsync \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir -r /app/requirements.lock

COPY *.py /app/
COPY static /app/static

RUN groupadd --gid 10001 homecontrol \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /tmp homecontrol

USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE=1 HOME=/tmp

EXPOSE 5000
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 CMD ["python", "backend_healthcheck.py", "--mode", "workers"]
ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "--config", "gunicorn_conf.py", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "--timeout", "600", "--access-logfile", "-", "--error-logfile", "-", "wsgi:app"]
