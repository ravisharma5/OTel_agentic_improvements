# TMF628 Performance Management MCP server container image
# Build context: mcp/tmf628/ directory
# Usage: podman build -t mcp-tmf628:latest -f mcp/tmf628/Dockerfile mcp/tmf628/

FROM python:3.12-slim

# Copy uv for fast, reproducible dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Layer caching: copy dependency manifests first, install, then copy source
COPY pyproject.toml uv.lock ./

# Install production dependencies (frozen lockfile for reproducible builds)
RUN uv sync --no-dev --frozen

# Copy server source, spec, and allowlist
COPY server.py ./
COPY specs/ ./specs/
COPY allowlist.yaml ./

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
