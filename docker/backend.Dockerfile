FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_CACHE_DIR=/home/supportdoc/.cache/uv \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    SUPPORTDOC_LOCAL_API_MODE=fixture \
    SUPPORTDOC_LOCAL_API_HOST=0.0.0.0 \
    SUPPORTDOC_LOCAL_API_PORT=9001 \
    SUPPORTDOC_QUERY_GENERATION_MODE=fixture

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system supportdoc \
    && useradd --system --create-home --gid supportdoc --home-dir /home/supportdoc supportdoc

RUN pip install --no-cache-dir "uv==0.10.9"

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --extra embeddings-local

COPY docs/contracts ./docs/contracts
COPY scripts ./scripts

RUN chmod +x scripts/run-api-local.sh \
    && chown -R supportdoc:supportdoc /app /home/supportdoc

USER supportdoc

EXPOSE 9001

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import json, urllib.request; response = urllib.request.urlopen('http://127.0.0.1:9001/healthz', timeout=3); payload = json.load(response); raise SystemExit(0 if payload.get('status') == 'ok' else 1)"

CMD ["./scripts/run-api-local.sh", "--host", "0.0.0.0", "--port", "9001"]
