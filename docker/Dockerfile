# syntax=docker/dockerfile:1
# LocalDrop production image.
#
# Multi-stage:
#   1. web     — builds the React/Vite SPA into backend/src/localdrop/static/
#   2. runtime — Python 3.12 slim, non-root, tini init, healthcheck
#
# The image version is injected at build time so nothing here hard-codes it:
#   docker build -f docker/Dockerfile \
#     --build-arg LOCALDROP_VERSION=1.1.0 \
#     --build-arg VCS_REF="$(git rev-parse --short HEAD)" \
#     -t ghcr.io/abhi-subedi/localdrop:1.1.0 .
#
# Releases are built by .github/workflows/release.yml with buildx for
# linux/amd64 and linux/arm64, then pushed to ghcr.io. Do not add a literal
# version string to this file: scripts/check_version.py fails the build if you do.

ARG NODE_VERSION=22-alpine
ARG PYTHON_VERSION=3.12-slim

# ---------- stage 1: frontend ----------
FROM node:${NODE_VERSION} AS web
WORKDIR /repo
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci --no-audit --no-fund
COPY frontend/ ./frontend/
COPY backend/ ./backend/
# vite outDir is backend/src/localdrop/static (see frontend/vite.config.ts)
RUN cd frontend && npm run build \
    && test -f ../backend/src/localdrop/static/index.html \
    || (echo "SPA build produced no index.html" && exit 1)

# ---------- stage 2: runtime ----------
FROM python:${PYTHON_VERSION} AS runtime

ARG LOCALDROP_VERSION=dev
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown

LABEL org.opencontainers.image.title="LocalDrop" \
      org.opencontainers.image.description="Self-hosted, local-network-first file sharing." \
      org.opencontainers.image.version="${LOCALDROP_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.source="https://github.com/Abhi-Subedi/LocalDrop" \
      org.opencontainers.image.url="https://github.com/Abhi-Subedi/LocalDrop" \
      org.opencontainers.image.documentation="https://github.com/Abhi-Subedi/LocalDrop/blob/main/docs/INSTALLATION.md"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend/src \
    LOCALDROP_DATA_DIR=/data \
    LOCALDROP_PORT=8080 \
    LOCALDROP_VERSION=${LOCALDROP_VERSION}

RUN apt-get update \
    && apt-get install -y --no-install-recommends tini curl postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -u 1000 -m localdrop \
    && mkdir -p /data /app/backend \
    && chown -R 1000:1000 /data /app

WORKDIR /app/backend
COPY backend/pyproject.toml ./
COPY backend/README.md ./README.md
COPY backend/src/ ./src/
# The wheel carries the built SPA and the Alembic environment, so a plain
# `pip install .` is all that is needed - no side-by-side COPY of static/ or
# migrations/ that could drift from the package.
RUN pip install --no-cache-dir . \
    && pip check \
    && rm -rf /root/.cache

COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

VOLUME ["/data"]
EXPOSE 8080

USER 1000:1000
ENTRYPOINT ["/usr/bin/tini", "--", "/app/entrypoint.sh"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://127.0.0.1:8080/api/v1/health/ready || exit 1
