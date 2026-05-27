FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KANBAN_HOST=0.0.0.0 \
    KANBAN_PORT=8080 \
    KANBAN_DATA=/data/board.json

WORKDIR /app

COPY app ./app

RUN useradd --create-home --uid 10001 kanban \
    && mkdir -p /data \
    && chown -R kanban:kanban /data /app

USER kanban

EXPOSE 8080

CMD ["python", "-m", "app.server"]
