FROM node:22-bookworm-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/index.html frontend/vite.config.js ./
COPY frontend/src ./src
COPY frontend/tests ./tests
RUN npm test && npm run build

FROM python:3.14-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml *.py ./
RUN python -m pip install --no-cache-dir .
COPY benchmarks ./benchmarks
COPY --from=frontend /frontend/dist ./frontend/dist
RUN useradd --create-home --uid 10001 impactlens
USER impactlens
EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "exec python -m uvicorn web:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]

FROM runtime AS test
USER root
COPY tests ./tests
RUN python -m pip install --no-cache-dir '.[test]'
USER impactlens
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]

FROM runtime AS production
