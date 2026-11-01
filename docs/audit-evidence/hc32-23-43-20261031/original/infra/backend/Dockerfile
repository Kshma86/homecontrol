FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client rsync \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY *.py /app/
COPY static /app/static

RUN groupadd --gid 10001 homecontrol \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /tmp homecontrol

USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE=1 HOME=/tmp

EXPOSE 5000
ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "--config", "gunicorn_conf.py", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "--timeout", "600", "--access-logfile", "-", "--error-logfile", "-", "wsgi:app"]
