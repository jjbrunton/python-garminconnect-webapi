# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates build-essential && \
    rm -rf /var/lib/apt/lists/*

# Copy project metadata and source required to build the wheel
COPY pyproject.toml /app/pyproject.toml
COPY README.md /app/README.md
COPY garminconnect /app/garminconnect

# Install runtime deps and the package with API extras
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .[api]

# Copy API app
COPY api /app/api

# Expose and run
EXPOSE 8000
ENV GARMINTOKENS=/data/.garminconnect
VOLUME ["/data"]

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
