FROM python:3.12.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
LABEL org.opencontainers.image.authors="Hystax"

WORKDIR /usr/src/app/

COPY optscale_client optscale_client

COPY gemini/__init__.py ./gemini/
COPY gemini/gemini_scheduler/pyproject.toml ./gemini/gemini_scheduler/
COPY gemini/gemini_scheduler/uv.lock ./gemini/gemini_scheduler/
COPY gemini/gemini_scheduler/*.py ./gemini/gemini_scheduler/

RUN uv --project gemini/gemini_scheduler sync --locked --no-dev

CMD ["uv", "run", "--project", "gemini/gemini_scheduler", "python", "-u","/usr/src/app/gemini/gemini_scheduler/main.py"]
