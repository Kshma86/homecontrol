FROM python@sha256:6c4dd321d176d61ea848dc8c73a4f7dbae8f70e0ee48bb411ea2f045b599fa8e

WORKDIR /app

COPY apps/ai-server/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir -r /app/requirements.lock
COPY apps/ai-server/ai_images.py /app/ai_images.py

COPY apps/ai-server/ai_server.py /app/ai_server.py
COPY apps/ai-server/ai_intents.py /app/ai_intents.py
COPY infra/backend/ai_domain_replies.py /app/ai_domain_replies.py
COPY infra/backend/ai_context_plan.py /app/ai_context_plan.py

EXPOSE 8088
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8088/health/live', timeout=2).close()"]
ENV PYTHONUNBUFFERED=1

CMD ["python", "ai_server.py"]
