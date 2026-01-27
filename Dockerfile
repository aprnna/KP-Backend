# Base image
FROM python:3.10-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install uv
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/* \
 && curl -LsSf https://astral.sh/uv/install.sh | sh \
 && ln -s /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app

# Hanya file deps untuk cache layer
COPY pyproject.toml ./
COPY uv.lock ./

# Buat venv sistem dan install deps tanpa dev
RUN uv sync --frozen --no-dev

# Copy kode
COPY app ./app

# Re-sync untuk memastikan editable paths terinclude
RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["uv", "run", "fastapi", "run"]
