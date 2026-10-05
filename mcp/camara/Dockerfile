# MCP-CAMARA container image
# Build context: mcp/camara/ directory
# Usage: podman build -t mcp-camara:latest -f mcp/camara/Dockerfile mcp/camara/
#
# Per D-10a: explicit @mcp.tool() server (not CLI-generated)

FROM python:3.12-slim

# Copy uv for fast, reproducible dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Layer caching: copy dependency manifest first, install, then copy source
COPY pyproject.toml ./

# Install production dependencies only
RUN uv sync --no-dev

# Copy server source
COPY server.py ./

# Copy spec files (reference/documentation)
COPY specs/ ./specs/

# Copy allowlist configs (documentation only for this server)
COPY allowlist_verify.yaml ./
COPY allowlist_retrieve.yaml ./

# OpenShift arbitrary-UID support:
# OpenShift runs containers with a randomly assigned UID in the root group (GID 0).
# Grant group-writable permissions so any UID in group 0 can read/write /app.
RUN chgrp -R 0 /app && chmod -R g=u /app

# Create explicit cache directories for uv and Python, also group-writable
RUN mkdir -p /app/.cache /app/.local && chgrp -R 0 /app/.cache /app/.local && chmod -R g=u /app/.cache /app/.local

# Redirect uv cache to a writable location
ENV UV_CACHE_DIR=/app/.cache/uv

# Prevent __pycache__ write attempts entirely
ENV PYTHONDONTWRITEBYTECODE=1

# Use numeric UID (OpenShift convention for arbitrary-UID images)
USER 1001

EXPOSE 8000

CMD ["uv", "run", "python", "server.py"]
