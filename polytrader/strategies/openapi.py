"""OpenAPI schema generation for strategy parameter schemas.

Per Commit 20: Standalone function for converting ParameterSchema to OpenAPI
JSON Schema format. Enables API documentation and client code generation.

This module provides pure functions (no side effects, deterministic) for
converting internal parameter definitions to OpenAPI-compatible schemas.
"""

from __future__ import annotations

from typing import Any

from polytrader.strategies.schema import ParameterSchema


def parameter_schema_to_openapi(schema: ParameterSchema) -> dict[str, Any]:
    """Convert ParameterSchema to OpenAPI 3.0 JSON Schema format.

    Per Commit 20: This function converts internal ParameterSchema definitions
    to OpenAPI-compatible JSON Schema for API documentation and client generation.

    Args:
        schema: ParameterSchema instance to convert

    Returns:
        OpenAPI JSON Schema dictionary with:
        - type: "object"
        - properties: Dictionary mapping parameter names to property definitions
        - required: List of required parameter names (only if any are required)

    Example:
        >>> from polytrader.strategies.schema import ParameterSchema, ParameterDefinition
        >>> schema = ParameterSchema(
        ...     parameters={
        ...         "buy_threshold": ParameterDefinition(
        ...             name="buy_threshold",
        ...             type=float,
        ...             required=False,
        ...             default=0.30,
        ...             description="Price threshold for BUY signals",
        ...             min_value=0.0,
        ...             max_value=1.0,
        ...         )
        ...     }
        ... )
        >>> openapi_schema = parameter_schema_to_openapi(schema)
        >>> assert openapi_schema["type"] == "object"
        >>> assert "buy_threshold" in openapi_schema["properties"]
        >>> assert openapi_schema["properties"]["buy_threshold"]["type"] == "number"
        >>> assert openapi_schema["properties"]["buy_threshold"]["default"] == 0.30

    Note:
        This is a pure function (no side effects, deterministic).
        Type mapping:
        - int → "integer"
        - float → "number"
        - str → "string"
        - bool → "boolean"
        - unknown types → "string" (fallback)
    """
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param_def in schema.parameters.items():
        # Map Python types to OpenAPI types
        openapi_type: str
        if param_def.type is int:
            openapi_type = "integer"
        elif param_def.type is float:
            openapi_type = "number"
        elif param_def.type is str:
            openapi_type = "string"
        elif param_def.type is bool:
            openapi_type = "boolean"
        else:
            # Fallback for unknown types
            openapi_type = "string"

        prop: dict[str, Any] = {
            "type": openapi_type,
            "description": param_def.description,
        }

        # Add default if provided
        if param_def.default is not None:
            prop["default"] = param_def.default

        # Add min/max for numeric types
        if param_def.type is int or param_def.type is float:
            if param_def.min_value is not None:
                prop["minimum"] = param_def.min_value
            if param_def.max_value is not None:
                prop["maximum"] = param_def.max_value

        properties[param_name] = prop

        # Add to required list if parameter is required
        if param_def.required:
            required.append(param_name)

    openapi_schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }

    # Only include "required" if there are required parameters
    if required:
        openapi_schema["required"] = required

    return openapi_schema
