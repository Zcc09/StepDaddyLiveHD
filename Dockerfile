ARG PORT=30000
ARG PROXY_CONTENT=TRUE
ARG SOCKS5
ARG API_URL

FROM python:3.13 AS builder

# Set Node memory limit to prevent GitHub runner hang
ENV NODE_OPTIONS="--max-old-space-size=4096"

RUN mkdir -p /app/.web
RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install requirements
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# --- CRITICAL FIX START ---
# Force downgrade Pydantic and SQLModel to versions compatible with Reflex 0.8.13
# This avoids the 'PydanticDeprecatedSince211' error
RUN pip install "pydantic<2.11.0" "sqlmodel<=0.0.22" "reflex==0.8.13"
# --- CRITICAL FIX END ---

COPY rxconfig.py ./
RUN reflex init

# Copy local context
COPY . .

ARG PORT API_URL PROXY_CONTENT SOCKS5
RUN REFLEX_API_URL=${API_URL:-http://localhost:$PORT} \
    reflex export --loglevel info --frontend-only --no-zip && \
    mv .web/build/client/* /srv/ && \
    rm -rf .web

# Final image
FROM python:3.13-slim

RUN apt-get update -y && apt-get install -y caddy redis-server && rm -rf /var/lib/apt/lists/*

ARG PORT API_URL
ENV PATH="/app/.venv/bin:$PATH" \
    PORT=$PORT \
    REFLEX_API_URL=${API_URL:-http://localhost:$PORT} \
    REDIS_URL=redis://localhost \
    PYTHONUNBUFFERED=1 \
    PROXY_CONTENT=${PROXY_CONTENT:-TRUE} \
    SOCKS5=${SOCKS5:-""}

WORKDIR /app
COPY --from=builder /app /app
COPY --from=builder /srv /srv

STOPSIGNAL SIGKILL
EXPOSE $PORT

# Using JSON syntax for CMD as recommended by Docker warnings
CMD ["sh", "-c", "caddy start && redis-server --daemonize yes && exec reflex run --env prod --backend-only"]
