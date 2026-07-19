FROM python:3.13-slim-trixie
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN uv --version

RUN apt-get update \
    && apt-get install --no-install-recommends -y poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./

ENV UV_NO_DEV=1
ENV UV_CACHE_DIR=/root/.cache/uv
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked

ENV PATH="/app/.venv/bin:$PATH"

COPY config.yaml config.yaml
COPY src/ .

CMD ["python", "app.py"]
