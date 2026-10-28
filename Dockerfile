# Stage 1: Build the Vue application
FROM node:22-alpine AS frontend-builder
WORKDIR /web-ui
COPY web-ui/package*.json ./
# Use CN mirror: official npm registry is slow/unreachable from CN networks.
# Cache mount keeps the npm download cache across builds even when this layer
# is invalidated (e.g. package.json changes).
RUN --mount=type=cache,target=/root/.npm npm ci --registry=https://registry.npmmirror.com
COPY web-ui/ .
RUN npm run build

# Stage 2: Build the python environment with dependencies
FROM python:3.11-slim-bookworm AS builder

# 设置环境变量以防止交互式提示
ENV DEBIAN_FRONTEND=noninteractive \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# 创建虚拟环境并安装 Python 运行时依赖
RUN python3 -m venv $VIRTUAL_ENV
COPY requirements-runtime.txt .
# Use Aliyun mirror: tuna blocks this host's egress IP with 403.
# Cache mount keeps downloaded wheels across builds; without it, every
# requirements change re-downloads ~200MB at mirror throttling speeds.
RUN --mount=type=cache,target=/root/.cache/pip pip install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements-runtime.txt

# Stage 3: Create the final, lean image
FROM python:3.11-slim-bookworm

WORKDIR /app
ENV DEBIAN_FRONTEND=noninteractive \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    RUNNING_IN_DOCKER=true \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    TZ=Asia/Shanghai

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

# Use CN mirror for Chromium download: official Playwright CDN is slow/unreachable from CN networks
ENV PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright
# Swap Debian apt sources to the Aliyun mirror: deb.debian.org throttles/fails
# from CN networks at peak hours (breaks apt-get and playwright --with-deps).
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        tzdata \
        tini \
        libzbar0 \
    && playwright install --with-deps --no-shell chromium \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=frontend-builder /dist /app/dist

COPY src /app/src
COPY spider_v2.py /app/spider_v2.py
COPY prompts /app/prompts
COPY static /app/static
COPY config.json.example /app/config.json.example

RUN mkdir -p /app/data /app/state /app/logs /app/images /app/jsonl /app/price_history

EXPOSE 8000

USER root

ENTRYPOINT ["tini", "--"]

CMD ["python", "-m", "src.app"]
