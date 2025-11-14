FROM python:3.12.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
LABEL org.opencontainers.image.authors="Hystax"

WORKDIR /usr/src/app/

COPY optscale_client optscale_client

COPY insider/__init__.py insider/
COPY insider/insider_worker/pyproject.toml insider/insider_worker/
COPY insider/insider_worker/uv.lock insider/insider_worker/
COPY insider/insider_worker/*.py ./insider/insider_worker/
COPY insider/insider_worker/migrations insider/insider_worker/migrations
COPY insider/insider_worker/processors insider/insider_worker/processors
COPY insider/insider_worker/http_client insider/insider_worker/http_client

RUN uv --project insider/insider_worker sync --locked --no-dev

CMD ["uv", "run", "--project", "insider/insider_worker", "python", "-u","/usr/src/app/insider/insider_worker/main.py"]
