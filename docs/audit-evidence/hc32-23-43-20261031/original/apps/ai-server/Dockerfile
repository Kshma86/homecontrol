FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir Pillow==11.3.0
COPY apps/ai-server/ai_images.py /app/ai_images.py

COPY apps/ai-server/ai_server.py /app/ai_server.py
COPY apps/ai-server/ai_intents.py /app/ai_intents.py
COPY infra/backend/ai_domain_replies.py /app/ai_domain_replies.py
COPY infra/backend/ai_context_plan.py /app/ai_context_plan.py

EXPOSE 8088
ENV PYTHONUNBUFFERED=1

CMD ["python", "ai_server.py"]
