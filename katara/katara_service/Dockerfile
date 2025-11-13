FROM python:3.12.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
LABEL org.opencontainers.image.authors="Hystax"

WORKDIR /usr/src/app/

COPY tools tools
COPY optscale_client optscale_client

COPY katara/__init__.py katara/

WORKDIR /usr/src/app/katara/katara_service

COPY katara/katara_service/pyproject.toml .
COPY katara/katara_service/uv.lock .
COPY katara/katara_service/alembic ./alembic
COPY katara/katara_service/controllers ./controllers
COPY katara/katara_service/handlers ./handlers
COPY katara/katara_service/models ./models
COPY katara/katara_service/*.py ./
COPY katara/katara_service/alembic.template .
COPY katara/katara_service/swagger ./swagger

WORKDIR /usr/src/app/

RUN uv --project katara/katara_service sync --locked --no-dev
RUN uv --project katara/katara_service run python -u katara/katara_service/write_spec.py

CMD ["uv", "run", "--project", "katara/katara_service", "python", "-u","/usr/src/app/katara/katara_service/main.py"]
EXPOSE 8935
