FROM python:3.12.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /usr/src/app/

COPY tools tools
COPY optscale_client optscale_client

COPY rest_api/__init__.py rest_api/__init__.py
COPY rest_api/live_demo.tar.xz rest_api/live_demo.tar.xz
COPY rest_api/google_calendar_client rest_api/google_calendar_client
COPY rest_api/rest_api_server/alembic rest_api/rest_api_server/alembic
COPY rest_api/rest_api_server/controllers rest_api/rest_api_server/controllers
COPY rest_api/rest_api_server/handlers rest_api/rest_api_server/handlers
COPY rest_api/rest_api_server/models rest_api/rest_api_server/models
COPY rest_api/rest_api_server/*.py rest_api/rest_api_server/
COPY rest_api/rest_api_server/alembic.template rest_api/rest_api_server/alembic.template
COPY rest_api/rest_api_server/swagger rest_api/rest_api_server/swagger
COPY rest_api/rest_api_server/recommendation_cleanup_scripts rest_api/rest_api_server/recommendation_cleanup_scripts

COPY rest_api/pyproject.toml rest_api/pyproject.toml
COPY rest_api/uv.lock rest_api/uv.lock

RUN uv --project rest_api sync --locked --no-dev
RUN uv --project rest_api run python -u rest_api/rest_api_server/write_spec.py

CMD ["uv", "--project", "rest_api", "run", "python", "-u", "/usr/src/app/rest_api/rest_api_server/server.py"]
EXPOSE 8999
