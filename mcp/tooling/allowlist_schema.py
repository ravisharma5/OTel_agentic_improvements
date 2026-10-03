"""Pydantic models for YAML/JSON allowlist configuration.

Defines the schema for OpenAPI operation filtering used by the
openapi_to_mcp.py conversion CLI. Each allowlist config specifies
which OpenAPI operations to expose as MCP tools, using RouteMap
filtering with an explicit catch-all EXCLUDE for unlisted operations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class OperationFilter(BaseModel):
    """An OpenAPI operation to include as an MCP component.

    Maps to a FastMCP RouteMap entry in the generated scaffold.
    Unlisted operations are excluded via a catch-all RouteMap(mcp_type=MCPType.EXCLUDE).
    """

    path: str = Field(
        ...,
        description="OpenAPI path, e.g. '/verify'",
    )
    methods: list[str] = Field(
        ...,
        description="HTTP methods to include, e.g. ['POST']",
    )
    mcp_type: Literal["TOOL", "RESOURCE", "PROMPT", "EXCLUDE"] = Field(
        default="TOOL",
        description="MCPType enum value for this operation",
    )


class AllowlistConfig(BaseModel):
    """Configuration for OpenAPI-to-MCP conversion.

    Loaded from a YAML file by the conversion CLI. Specifies which
    operations from the OpenAPI spec to expose as MCP tools, and
    how the generated scaffold connects to its backend.
    """

    server_name: str = Field(
        ...,
        description="FastMCP server name used in the generated scaffold",
    )
    spec_path: str = Field(
        ...,
        description="Path to the OpenAPI spec file (relative or absolute)",
    )
    backend_env_var: str = Field(
        ...,
        description="ConfigMap key name for backend URL, e.g. 'CAMARA_BASE_URL'",
    )
    operations: list[OperationFilter] = Field(
        ...,
        description="Operations to include as MCP tools; unlisted operations are excluded",
    )


def load_allowlist(path: str) -> AllowlistConfig:
    """Load and validate an allowlist config from a YAML file.

    Args:
        path: Path to the YAML allowlist config file.

    Returns:
        Validated AllowlistConfig instance.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        yaml.YAMLError: If the file is not valid YAML.
        pydantic.ValidationError: If the YAML does not match the schema.
    """
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text())
    return AllowlistConfig(**raw)
