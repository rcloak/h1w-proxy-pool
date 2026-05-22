FROM ghcr.io/astral-sh/uv:0.5.31 AS uv

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

COPY --from=uv /uv /uvx /bin/

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md /app/

RUN uv sync --frozen --no-dev --no-install-project

COPY proxy_pool /app/proxy_pool
COPY config.ini /app/config.ini
COPY scrap_proxies.py web_server.py /app/

RUN uv sync --frozen --no-dev \
    && groupadd --system proxypool \
    && useradd --system --gid proxypool --home-dir /app --shell /usr/sbin/nologin proxypool \
    && mkdir -p /app/data \
    && chown -R proxypool:proxypool /app/data /app/.venv

USER proxypool

EXPOSE 5000

CMD ["/app/.venv/bin/uvicorn", "proxy_pool.app:app", "--host", "0.0.0.0", "--port", "5000"]
