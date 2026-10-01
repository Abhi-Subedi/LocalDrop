# LocalDrop V1 production image.
#
# Multi-stage:
#   1. web — builds the React/Vite SPA into backend/static/
#   2. runtime — Python 3.12 slim, non-root, tini init, healthcheck
#
# Run from the repo root:  docker build -f docker/Dockerfile -t localdrop:1.0.0 .

# ---------- stage 1: frontend ----------
FROM node:20-alpine AS web
WORKDIR /repo
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci --no-audit --no-fund
COPY frontend/ ./frontend/
COPY backend/ ./backend/
# vite outDir is ../backend/static (see frontend/vite.config.ts)
RUN cd frontend && npm run build && ls -la ../backend/static/index.html

# ---------- stage 2: runtime ----------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend/src \
    LOCALDROP_DATA_DIR=/data \
    LOCALDROP_PORT=8080

RUN apt-get update \
    && apt-get install -y --no-install-recommends tini curl postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -u 1000 -m localdrop \
    && mkdir -p /data /app/backend \
    && chown -R 1000:1000 /data /app

WORKDIR /app/backend
COPY backend/pyproject.toml backend/alembic.ini ./
COPY backend/migrations/ ./migrations/
RUN pip install --no-cache-dir . \
    && pip check \
    && rm -rf /root/.cache

COPY --from=web --chown=1000:1000 /repo/backend/static/ ./static/
COPY --from=web --chown=1000:1000 /repo/backend/src/ ./src/
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

VOLUME ["/data"]
EXPOSE 8080

USER 1000:1000
ENTRYPOINT ["/usr/bin/tini", "--", "/app/entrypoint.sh"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://127.0.0.1:8080/api/v1/health/ready || exit 1
