FROM python:3.12.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
LABEL org.opencontainers.image.authors="Hystax"

WORKDIR /usr/src/app/

COPY optscale_client optscale_client
COPY tools tools

COPY bumischeduler/pyproject.toml bumischeduler/pyproject.toml
COPY bumischeduler/uv.lock bumischeduler/uv.lock
COPY bumischeduler/*.py ./bumischeduler/
COPY bumischeduler/bumischeduler/controllers bumischeduler/bumischeduler/controllers
COPY bumischeduler/bumischeduler/*.py ./bumischeduler/bumischeduler/

RUN uv --project bumischeduler sync --locked --no-dev

CMD ["uv", "run", "--project", "bumischeduler", "python", "-u","/usr/src/app/bumischeduler/bumischeduler/main.py"]
