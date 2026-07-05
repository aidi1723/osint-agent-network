FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app/backend

COPY backend /app/backend
COPY scripts /app/scripts

EXPOSE 8088

CMD ["python", "-m", "app.main"]
