FROM python:3.12.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
LABEL org.opencontainers.image.authors="Hystax"

ENV PYTHONUNBUFFERED 1

WORKDIR /usr/src/app/

COPY optscale_client optscale_client
COPY tools tools

COPY bi_exporter/pyproject.toml bi_exporter/pyproject.toml
COPY bi_exporter/uv.lock bi_exporter/uv.lock
COPY bi_exporter/__init__.py bi_exporter/__init__.py

COPY bi_exporter/bumblebi bi_exporter/bumblebi

RUN uv --project bi_exporter sync --locked --no-dev

CMD ["uv", "run", "--project", "bi_exporter", "python", "-u","/usr/src/app/bi_exporter/bumblebi/exporter/main.py"]
