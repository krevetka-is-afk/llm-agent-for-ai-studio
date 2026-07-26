FROM python:3.13-slim-trixie
COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /uvx /bin/

RUN uv --version

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./

ENV UV_NO_DEV=1
ENV UV_CACHE_DIR=/root/.cache/uv
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1

RUN addgroup --system app \
    && adduser --system --ingroup app app \
    && mkdir -p /data /app/uploaded_files \
    && chown -R app:app /app /data

COPY --chown=app:app config.yaml config.yaml
COPY --chown=app:app .streamlit .streamlit
COPY --chown=app:app src/ .

USER app

CMD ["python", "app.py"]
