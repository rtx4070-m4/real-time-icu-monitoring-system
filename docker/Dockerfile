# ─── Stage 1: Builder ────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt


# ─── Stage 2: Runtime ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="ICU Monitoring System"
LABEL description="Real-Time Smart ICU Monitoring System — FAANG-level"

# Non-root user for security
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY backend/ /app/

# Copy frontend (served by uvicorn as static in prod)
COPY frontend/ /app/static/

# Create data directory for SQLite
RUN mkdir -p /data && chown appuser:appuser /data

USER appuser

ENV DATABASE_URL=sqlite:////data/icu.db
ENV API_HOST=0.0.0.0
ENV API_PORT=8000
ENV LOG_LEVEL=INFO
ENV PATIENT_COUNT=8

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
