# build: docker build -f guidance-relevance-web/Dockerfile .
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0

WORKDIR /src
COPY guidance-relevance-filter /src/guidance-relevance-filter
COPY guidance-relevance-web /src/guidance-relevance-web

WORKDIR /src/guidance-relevance-web
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable \
 && .venv/bin/python -c "import nltk; nltk.download('stopwords', download_dir='/nltk_data')"

FROM python:3.12-slim-bookworm

ENV PATH="/src/guidance-relevance-web/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    NLTK_DATA=/usr/share/nltk_data \
    GRF_HOST=0.0.0.0 \
    GRF_PORT=8000 \
    GRF_CORPUS=/data/corpus \
    GRF_JOBS=/data/jobs

COPY --from=builder /src/guidance-relevance-web/.venv /src/guidance-relevance-web/.venv
COPY --from=builder /nltk_data /usr/share/nltk_data

RUN useradd --system --uid 10001 --home /data app \
 && mkdir -p /data/corpus /data/jobs \
 && chown -R app:app /data
USER app
WORKDIR /data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["guidance-relevance-web"]
