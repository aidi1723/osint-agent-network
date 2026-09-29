FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    APP_HOST=0.0.0.0 \
    OSINT_DB_PATH=/app/data/osint.sqlite \
    JOB_WORKDIR=/app/data/jobs

WORKDIR /app/backend

COPY backend /app/backend
COPY scripts /app/scripts

EXPOSE 8088

CMD ["python", "-m", "app.main"]
