FROM python:3.12.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
LABEL org.opencontainers.image.authors="Hystax"

WORKDIR /usr/src/app/

COPY optscale_client optscale_client

COPY insider/__init__.py insider/
COPY insider/insider_scheduler/pyproject.toml insider/insider_scheduler/
COPY insider/insider_scheduler/uv.lock insider/insider_scheduler/
COPY insider/insider_scheduler/*.py ./insider/insider_scheduler/

RUN uv --project insider/insider_scheduler sync --locked --no-dev

CMD ["uv", "run", "--project", "insider/insider_scheduler", "python", "-u","/usr/src/app/insider/insider_scheduler/main.py"]
