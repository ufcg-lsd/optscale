FROM python:3.12.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /usr/src/app/

COPY jira_bus/pyproject.toml jira_bus/pyproject.toml
COPY jira_bus/uv.lock jira_bus/uv.lock
COPY jira_bus/__init__.py jira_bus/__init__.py

COPY optscale_client optscale_client
COPY tools tools

RUN uv --project jira_bus sync --locked --no-dev

WORKDIR /usr/src/app/jira_bus/jira_bus_server

COPY jira_bus/jira_bus_server/swagger ./swagger
COPY jira_bus/jira_bus_server/alembic.template ./
COPY jira_bus/jira_bus_server/*.py ./
COPY jira_bus/jira_bus_server/alembic ./alembic
COPY jira_bus/jira_bus_server/models ./models
COPY jira_bus/jira_bus_server/ui ./ui
COPY jira_bus/jira_bus_server/handlers ./handlers
COPY jira_bus/jira_bus_server/controllers ./controllers
COPY jira_bus/jira_bus_server/atlassian_client ./atlassian_client

WORKDIR /usr/src/app/
RUN uv --project jira_bus run python -u jira_bus/jira_bus_server/write_spec.py


CMD ["uv", "run", "--project", "jira_bus", "python", "/usr/src/app/jira_bus/jira_bus_server/server.py"]
