FROM python:3.12.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
LABEL org.opencontainers.image.authors="Hystax"

WORKDIR /usr/src/app/

COPY optscale_client optscale_client

COPY diproxy/pyproject.toml diproxy/pyproject.toml
COPY diproxy/uv.lock diproxy/uv.lock
COPY diproxy/*.py ./diproxy/
COPY diproxy/diproxy/*.py ./diproxy/diproxy/
COPY diproxy/diproxy/swagger diproxy/diproxy/swagger

RUN uv --project diproxy sync --locked --no-dev
RUN uv --project diproxy run python -u diproxy/diproxy/write_spec.py

CMD ["uv", "run", "--project", "diproxy", "python", "-u","/usr/src/app/diproxy/diproxy/main.py"]
EXPOSE 8935
