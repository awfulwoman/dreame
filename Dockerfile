# Build stage: resolve dependencies with uv into a venv
FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
# piper by default; xtts pulls in torch (several GB)
ARG EXTRAS="piper"
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project $(printf -- '--extra %s ' $EXTRAS)
COPY dreame_voice/ ./dreame_voice/
RUN uv sync --frozen --no-dev --no-editable $(printf -- '--extra %s ' $EXTRAS)

# Runtime stage: the venv, the reference dialog and the voice files
FROM python:3.13-slim
# curl: robot.py talks to Valetudo through it
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --gid 1000 app \
 && useradd --uid 1000 --gid app --home-dir /app --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY archive/sounds.csv archive/sounds.csv
COPY archive/audio/firmware/ archive/audio/firmware/
COPY voices/ voices/
RUN mkdir build models && chown app:app build models
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION
USER app
# build/: generated audio and packs. models/: downloaded Piper models.
VOLUME ["/app/build", "/app/models"]
ENTRYPOINT ["dreame-voice"]
CMD ["list"]
