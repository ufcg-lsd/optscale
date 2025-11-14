FROM python:3.12.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /src

COPY tools tools
COPY optscale_client optscale_client

COPY slacker/pyproject.toml slacker/pyproject.toml
COPY slacker/uv.lock slacker/uv.lock
COPY slacker/__init__.py slacker/__init__.py

COPY slacker/slacker_server/swagger slacker/slacker_server/swagger
COPY slacker/slacker_server/alembic.template slacker/slacker_server/
COPY slacker/slacker_server/*.py slacker/slacker_server/
COPY slacker/slacker_server/alembic slacker/slacker_server/alembic
COPY slacker/slacker_server/models slacker/slacker_server/models
COPY slacker/slacker_server/message_templates slacker/slacker_server/message_templates
COPY slacker/slacker_server/handlers slacker/slacker_server/handlers
COPY slacker/slacker_server/controllers slacker/slacker_server/controllers

RUN uv --project slacker sync --locked --no-dev
RUN uv --project slacker run python -u slacker/slacker_server/write_spec.py

CMD ["uv", "run", "--project", "slacker", "python", "/src/slacker/slacker_server/server.py"]
