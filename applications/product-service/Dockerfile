# syntax=docker/dockerfile:1.7
# Build context: repository root -> docker build -f applications/product-service/Dockerfile .
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY applications/product-service/requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

FROM python:3.12-slim AS runtime
ARG APP_VERSION=1.0.0
LABEL org.opencontainers.image.title="product-service" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.vendor="Enterprise Kubernetes GitOps Platform"
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/shared:/app \
    APP_VERSION=${APP_VERSION}
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=10001:10001 applications/shared /app/shared
COPY --chown=10001:10001 applications/product-service/app /app/app
USER 10001:10001
EXPOSE 8002
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import sys,urllib.request;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8002/health/live',timeout=2).status==200 else 1)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002", "--proxy-headers", "--no-access-log"]
