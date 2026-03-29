# Multi-stage production image (non-root). Use `alembic upgrade head` for schema — not create_all.
# docker build -t arctis:latest .

FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY pyproject.toml ./
COPY arctis ./arctis

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

RUN python -m compileall -q arctis

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash --uid 10001 arctis \
    && mkdir -p /home/arctis/data \
    && chown -R arctis:arctis /home/arctis

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /home/arctis
USER arctis

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV ENV=prod
ENV DATABASE_URL=sqlite+pysqlite:////home/arctis/data/arctis.db

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "arctis.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
