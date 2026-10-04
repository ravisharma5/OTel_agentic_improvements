# MCP-Telecom container image
# Build context: mcp/mcp-telecom/ directory
# Usage: podman build -t mcp-telecom:latest -f mcp/mcp-telecom/Dockerfile mcp/mcp-telecom/
#
# Per D-01 (HTTP transport), D-02 (vendor into repo, bake into image),
# D-03 (Streamable HTTP on port 8000), D-05 (FastMCP >= 4.0.0)

FROM python:3.12-slim

# Copy uv for fast, reproducible dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Layer caching: copy dependency manifests first, install, then copy source
# README.md is required by hatchling build backend (referenced in pyproject.toml)
COPY pyproject.toml uv.lock README.md ./

# Install production dependencies only (frozen lockfile, no dev deps)
RUN uv sync --no-dev --frozen

# Copy source code
COPY src/ ./src/

# Copy config scaffolds -- devices.yaml.example as devices.yaml for runtime
COPY devices.yaml.example ./devices.yaml
COPY command_allowlist.yaml ./command_allowlist.yaml

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

# Run via the pyproject.toml [project.scripts] entry point
CMD ["uv", "run", "mcp-telecom"]
