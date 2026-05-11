FROM python:3.12-slim-trixie
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN uv --version

COPY pyproject.toml uv.lock ./

ENV UV_NO_DEV=1
ENV UV_CACHE_DIR=/root/.cache/uv
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked

ENV PATH="/app/.venv/bin:$PATH"

WORKDIR app/
COPY .env .env
COPY src/ .

CMD ["uv", "run", "--env-file", ".env", "main.py"]
