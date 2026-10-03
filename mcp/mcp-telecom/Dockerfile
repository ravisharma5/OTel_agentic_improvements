FROM python:3.12-slim

LABEL maintainer="Avinash Amudala <aa9429@g.rit.edu>"
LABEL description="MCP-Telecom: AI-powered network equipment management"

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends openssh-client && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir hatchling

COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN pip install --no-cache-dir .

COPY devices.yaml.example devices.yaml.example

RUN mkdir -p logs backups

ENV MCP_TELECOM_DEVICES_FILE=/app/devices.yaml
ENV MCP_TELECOM_LOG_LEVEL=INFO
ENV MCP_TELECOM_AUDIT_LOG=/app/logs/audit.log

ENTRYPOINT ["mcp-telecom"]
