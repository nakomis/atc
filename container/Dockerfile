# syntax=docker/dockerfile:1
# Single ATC image: the API serves the built board. Mace is x86-64, so build with
# --platform linux/amd64, from the repository root: docker build -f container/Dockerfile .

FROM node:25-alpine AS web
WORKDIR /web
# Node 25 no longer ships corepack, so install the pnpm that package.json pins.
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN npm install -g "$(node -p "require('./package.json').packageManager")"
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY api/atc ./atc
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist /app/static
RUN useradd --uid 10001 --no-create-home atc && chown -R atc /app
USER atc
ENV ATC_STATIC_DIR=/app/static
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]
CMD ["uvicorn", "atc.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
