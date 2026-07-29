FROM python:3.12-slim

WORKDIR /app

COPY ai_server.py /app/ai_server.py

EXPOSE 8088
ENV PYTHONUNBUFFERED=1

CMD ["python", "ai_server.py"]
