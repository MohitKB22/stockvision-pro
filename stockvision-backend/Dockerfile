# =============================================================================
# FastAPI production image — multi-stage.
#
# The builder stage carries gcc/g++ (needed to build any package without a wheel
# for this platform); the runtime stage does not. Shipping a compiler in a
# production image is both ~400 MB of dead weight and a useful tool for an
# attacker who gets code execution.
# =============================================================================

FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc g++ libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# libpq5 (the runtime library) rather than libpq-dev (headers + compiler deps).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 libgomp1 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash --uid 1000 appuser

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=appuser:appuser . .

RUN mkdir -p /app/document_storage /app/ml_artifacts /app/report_storage \
 && chown -R appuser:appuser /app

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
  CMD curl -fsS http://localhost:8000/health/ready || exit 1

# --proxy-headers so the app trusts X-Forwarded-For from NGINX; without it the
# rate limiter and the audit log record the proxy's IP for every request.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
