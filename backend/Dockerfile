# Install uv
FROM python:3.14-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /uvx /bin/

# Use the system Python across both stages,
# Precompile bytecode for faster startup
# And copy from the cache mount instead of linking
ENV UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies only, so this layer is cached until uv.lock changes
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project --no-editable

# Copy only what is needed to build the project into the intermediate image
COPY pyproject.toml uv.lock ./
COPY src ./src

# Sync the project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:3.14-slim

# Copy the environment, but not the source code
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Run the application
CMD ["uvicorn", "notes_board.main:app", "--host", "0.0.0.0", "--port", "8000"]
