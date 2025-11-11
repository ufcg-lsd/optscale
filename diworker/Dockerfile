FROM python:3.12.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /src

COPY optscale_client optscale_client
COPY tools tools

COPY diworker/*.py diworker/
COPY diworker/pyproject.toml diworker/pyproject.toml
COPY diworker/uv.lock diworker/uv.lock
COPY diworker/diworker diworker/diworker

RUN uv --project diworker sync --locked --no-dev

# used to store the report being processed. Automatically deleted
VOLUME ["/src/reports"]

CMD ["uv", "run", "--project", "diworker", "/src/diworker/diworker/main.py"]
