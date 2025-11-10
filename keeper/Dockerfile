FROM python:3.12.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
LABEL org.opencontainers.image.authors="Hystax"

WORKDIR /usr/src/app/

COPY keeper/pyproject.toml keeper/pyproject.toml
COPY keeper/uv.lock keeper/uv.lock
COPY keeper/__init__.py keeper/__init__.py

COPY tools tools
COPY optscale_client optscale_client
RUN uv --project keeper sync --locked --no-dev

WORKDIR /usr/src/app/keeper/report_server
COPY keeper/report_server/controllers ./controllers
COPY keeper/report_server/handlers ./handlers
COPY keeper/report_server/swagger ./swagger
COPY keeper/report_server/*.py ./

WORKDIR /usr/src/app/
RUN uv --project keeper run python -u keeper/report_server/write_spec.py

CMD ["uv", "run", "--project", "keeper", "python", "-u","/usr/src/app/keeper/report_server/server.py"]
EXPOSE 8973
