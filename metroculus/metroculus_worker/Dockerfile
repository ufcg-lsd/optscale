FROM python:3.12.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
LABEL org.opencontainers.image.authors="Hystax"

WORKDIR /usr/src/app/

COPY optscale_client optscale_client
COPY tools tools

COPY metroculus/__init__.py metroculus/
COPY metroculus/metroculus_worker/pyproject.toml metroculus/metroculus_worker/
COPY metroculus/metroculus_worker/uv.lock metroculus/metroculus_worker/
COPY metroculus/metroculus_worker/*.py ./metroculus/metroculus_worker/
COPY metroculus/metroculus_worker/migrations metroculus/metroculus_worker/migrations

RUN uv --project metroculus/metroculus_worker sync --locked --no-dev

CMD ["uv", "run", "--project", "metroculus/metroculus_worker", "python", "-u","/usr/src/app/metroculus/metroculus_worker/main.py"]
