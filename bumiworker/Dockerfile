FROM python:3.12.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
LABEL org.opencontainers.image.authors="Hystax"

WORKDIR /usr/src/app/

COPY optscale_client optscale_client
COPY tools tools

COPY bumiworker/pyproject.toml bumiworker/pyproject.toml
COPY bumiworker/uv.lock bumiworker/uv.lock
COPY bumiworker/bumiworker/modules ./bumiworker/bumiworker/modules
COPY bumiworker/bumiworker/*.py ./bumiworker/bumiworker/
COPY bumiworker/*.py ./bumiworker/

RUN uv --project bumiworker sync --locked --no-dev

CMD ["uv", "run", "--project", "bumiworker", "python", "-u","/usr/src/app/bumiworker/bumiworker/main.py"]
