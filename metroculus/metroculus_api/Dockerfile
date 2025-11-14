FROM python:3.12.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
LABEL org.opencontainers.image.authors="Hystax"

WORKDIR /usr/src/app/

COPY tools tools
COPY optscale_client optscale_client

COPY metroculus/__init__.py metroculus/
COPY metroculus/metroculus_api/pyproject.toml metroculus/metroculus_api/
COPY metroculus/metroculus_api/uv.lock metroculus/metroculus_api/
COPY metroculus/metroculus_api/controllers metroculus/metroculus_api/controllers
COPY metroculus/metroculus_api/handlers metroculus/metroculus_api/handlers
COPY metroculus/metroculus_api/swagger metroculus/metroculus_api/swagger
COPY metroculus/metroculus_api/*.py metroculus/metroculus_api/

RUN uv --project metroculus/metroculus_api sync --locked --no-dev
RUN uv --project metroculus/metroculus_api run python -u metroculus/metroculus_api/write_spec.py

CMD ["uv", "run", "--project", "metroculus/metroculus_api", "python", "-u","/usr/src/app/metroculus/metroculus_api/server.py"]
EXPOSE 8969
