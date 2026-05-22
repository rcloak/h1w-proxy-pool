FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:$PATH"

COPY pyproject.toml uv.lock README.md /app/
COPY proxy_pool /app/proxy_pool
COPY config.ini /app/config.ini
COPY scrap_proxies.py web_server.py /app/

RUN uv sync --frozen --no-dev

EXPOSE 5000

CMD ["uv", "run", "uvicorn", "proxy_pool.app:app", "--host", "0.0.0.0", "--port", "5000"]
