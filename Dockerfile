# Disruption Copilot: one container. The backend (FastAPI) serves the API and the built website on one port.

# ---- 1. build the website
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. the app
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    COPILOT_DATA_DIR=/data FRONTEND_DIST=/app/frontend/dist PORT=8000
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist
COPY deploy/start.sh /app/start.sh
RUN chmod +x /app/start.sh && useradd -m app && mkdir -p /data && chown -R app /data /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health')"
CMD ["/app/start.sh"]
