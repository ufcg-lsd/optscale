FROM python:3.12.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
LABEL org.opencontainers.image.authors="Hystax"

WORKDIR /usr/src/app/

COPY tools tools
COPY optscale_client optscale_client

COPY risp/__init__.py ./risp/
ADD risp/risp_worker/migrations risp/risp_worker/migrations
COPY risp/risp_worker/pyproject.toml risp/risp_worker/
COPY risp/risp_worker/uv.lock risp/risp_worker/
COPY risp/risp_worker/*.py ./risp/risp_worker/
COPY risp/risp_worker/processors/*.py ./risp/risp_worker/processors/

RUN uv --project risp/risp_worker sync --locked --no-dev

CMD ["uv", "run", "--project", "risp/risp_worker", "python", "-u", "/usr/src/app/risp/risp_worker/worker.py"]
