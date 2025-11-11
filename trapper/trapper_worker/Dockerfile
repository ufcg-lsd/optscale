FROM python:3.12.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
LABEL org.opencontainers.image.authors="Hystax"

WORKDIR /usr/src/app/

COPY optscale_client optscale_client
COPY tools tools

COPY trapper/__init__.py ./trapper/
COPY trapper/trapper_worker/pyproject.toml ./trapper/trapper_worker/
COPY trapper/trapper_worker/uv.lock ./trapper/trapper_worker/
COPY trapper/trapper_worker/*.py ./trapper/trapper_worker/

RUN uv --project trapper/trapper_worker sync --locked --no-dev
CMD ["uv", "run", "--project", "trapper/trapper_worker", "python", "-u","/usr/src/app/trapper/trapper_worker/main.py"]
