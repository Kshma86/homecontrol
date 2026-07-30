FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client rsync \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app.py /app/app.py
COPY admin_service.py /app/admin_service.py
COPY api_route_modules.py /app/api_route_modules.py
COPY ai_proxy_service.py /app/ai_proxy_service.py
COPY ai_node_service.py /app/ai_node_service.py
COPY backup_service.py /app/backup_service.py
COPY climate_service.py /app/climate_service.py
COPY command_service.py /app/command_service.py
COPY context_service.py /app/context_service.py
COPY context_payload_service.py /app/context_payload_service.py
COPY database_service.py /app/database_service.py
COPY energy_device_service.py /app/energy_device_service.py
COPY irrigation_service.py /app/irrigation_service.py
COPY mqtt_monitor_service.py /app/mqtt_monitor_service.py
COPY power_wall_service.py /app/power_wall_service.py
COPY process_binding_service.py /app/process_binding_service.py
COPY repository_service.py /app/repository_service.py
COPY robot_service.py /app/robot_service.py
COPY scheduler_service.py /app/scheduler_service.py
COPY schema_service.py /app/schema_service.py
COPY startup_service.py /app/startup_service.py
COPY system_status_service.py /app/system_status_service.py
COPY static /app/static

EXPOSE 5000
ENV PYTHONUNBUFFERED=1

CMD ["python", "app.py"]
