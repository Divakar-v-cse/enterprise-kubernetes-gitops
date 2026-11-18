# syntax=docker/dockerfile:1.7
# Build context: repository root -> docker build -f applications/frontend/Dockerfile .
FROM node:20.18-alpine AS builder
WORKDIR /app
COPY applications/frontend/package.json applications/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY applications/frontend/tsconfig.json applications/frontend/tsconfig.node.json \
     applications/frontend/vite.config.ts applications/frontend/index.html ./
COPY applications/frontend/src ./src
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
LABEL org.opencontainers.image.title="frontend" \
      org.opencontainers.image.vendor="Enterprise Kubernetes GitOps Platform"
USER 101
COPY applications/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder --chown=101:101 /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD ["wget", "-qO-", "http://127.0.0.1:8080/healthz"]
CMD ["nginx", "-g", "daemon off;"]
