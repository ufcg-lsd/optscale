FROM python:3.12.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
LABEL org.opencontainers.image.authors="Hystax"

WORKDIR /usr/src/app/

COPY optscale_client optscale_client

COPY risp/__init__.py risp/
COPY risp/risp_scheduler/pyproject.toml risp/risp_scheduler/
COPY risp/risp_scheduler/uv.lock risp/risp_scheduler/
COPY risp/risp_scheduler/*.py risp/risp_scheduler/

RUN uv --project risp/risp_scheduler sync --locked --no-dev

CMD ["uv", "run", "--project", "risp/risp_scheduler", "python", "-u","/usr/src/app/risp/risp_scheduler/scheduler.py"]
