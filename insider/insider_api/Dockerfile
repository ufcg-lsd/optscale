FROM python:3.12.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
LABEL org.opencontainers.image.authors="Hystax"

WORKDIR /usr/src/app/

COPY optscale_client optscale_client
COPY tools tools

COPY insider/__init__.py insider/
COPY insider/insider_api/pyproject.toml insider/insider_api/
COPY insider/insider_api/uv.lock insider/insider_api/

COPY insider/insider_api/controllers insider/insider_api/controllers
COPY insider/insider_api/handlers insider/insider_api/handlers
COPY insider/insider_api/swagger insider/insider_api/swagger
COPY insider/insider_api/*.py insider/insider_api/
COPY insider/*.py insider/

RUN uv --project insider/insider_api sync --locked --no-dev
RUN uv --project insider/insider_api run python -u insider/insider_api/write_spec.py

CMD ["uv", "run", "--project", "insider/insider_api", "python", "-u","/usr/src/app/insider/insider_api/server.py"]
EXPOSE 8945
