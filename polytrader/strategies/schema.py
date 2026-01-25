"""Strategy parameter schema definitions and validation.

Per architecture.mdc: Strategy configurations must be validated at boundaries.
This module provides type-safe parameter definitions with explicit validation rules.

Per flows.mdc §4: Strategy parameters must be deterministic and testable.
All validation is pure (no side effects, no I/O).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, get_args, get_origin


class ValidationError(Exception):
    """Raised when parameter validation fails.

    Attributes:
        parameter_name: Name of the parameter that failed validation
        value: The invalid value
        reason: Human-readable reason for validation failure
    """

    def __init__(
        self,
        parameter_name: str,
        value: Any,
        reason: str,
    ) -> None:
        """Initialize ValidationError.

        Args:
            parameter_name: Name of the parameter
            value: The invalid value
            reason: Reason for failure
        """
        self.parameter_name = parameter_name
        self.value = value
        self.reason = reason
        message = f"{parameter_name}: {reason} (value: {value!r})"
        super().__init__(message)


@dataclass(frozen=True)
class ParameterDefinition:
    """Definition of a single strategy parameter.

    Per architecture.mdc: All strategy parameters must have explicit definitions
    with types, defaults, and validation rules.

    Attributes:
        name: Parameter name (must be valid Python identifier)
        type: Parameter type (float, int, str, bool, etc.)
        required: Whether parameter is required (if False, default must be provided)
        default: Default value (None if required=True, must be provided if required=False)
        description: Human-readable description of the parameter
        validation: Optional custom validation function (returns True if valid)
        min_value: Minimum value for numeric types (None if not applicable)
        max_value: Maximum value for numeric types (None if not applicable)
    """

    name: str
    type: type[Any]
    required: bool
    default: Any | None
    description: str
    validation: Callable[[Any], bool] | None = None
    min_value: float | int | None = None
    max_value: float | int | None = None

    def __post_init__(self) -> None:
        """Validate ParameterDefinition itself."""
        if not self.name:
            raise ValueError("Parameter name cannot be empty")

        if not self.required and self.default is None:
            raise ValueError(f"Parameter '{self.name}': default must be provided if required=False")

        if self.required and self.default is not None:
            raise ValueError(f"Parameter '{self.name}': default must be None if required=True")

        # Validate default type matches parameter type
        if self.default is not None:
            # self.type is a runtime value (type object), not a type annotation
            self._validate_type(self.default, self.type, self.name)

        # Validate min/max for numeric types
        if self.min_value is not None or self.max_value is not None:
            if self.type not in (float, int):
                raise ValueError(
                    f"Parameter '{self.name}': min_value/max_value only valid for numeric types"
                )

        if self.min_value is not None and self.max_value is not None:
            if self.min_value > self.max_value:
                raise ValueError(
                    f"Parameter '{self.name}': min_value ({self.min_value}) > "
                    f"max_value ({self.max_value})"
                )

    @staticmethod
    def _validate_type(
        value: Any,
        expected_type: type[Any] | Any,
        parameter_name: str,  # type: ignore[valid-type]
    ) -> None:
        """Validate that value matches expected type.

        Handles type hints like int | float, Optional[int], etc.
        """
        # Handle union types (int | float, Optional[int])
        origin = get_origin(expected_type)
        if origin is not None:
            # Union type - check against all possible types
            args = get_args(expected_type)
            if any(isinstance(value, arg) for arg in args if arg is not type(None)):
                return
            raise ValidationError(
                parameter_name,
                value,
                f"value must be one of {args}, got {type(value).__name__}",
            )

        # Handle direct type check
        if not isinstance(value, expected_type):
            type_name = getattr(expected_type, "__name__", str(expected_type))
            raise ValidationError(
                parameter_name,
                value,
                f"value must be {type_name}, got {type(value).__name__}",
            )

    def validate_value(self, value: Any) -> list[str]:
        """Validate a parameter value against this definition.

        Args:
            value: Value to validate

        Returns:
            List of error messages (empty if valid)

        Note:
            This is a pure function (no side effects, deterministic).
        """
        errors: list[str] = []

        # Type validation
        try:
            # self.type is a runtime value (type object), not a type annotation
            self._validate_type(value, self.type, self.name)
        except ValidationError as e:
            errors.append(str(e))
            return errors  # Don't continue validation if type is wrong

        # Numeric bounds validation
        if self.type in (float, int):
            if self.min_value is not None:
                if value < self.min_value:
                    errors.append(
                        f"{self.name}: value {value} is less than minimum {self.min_value}"
                    )

            if self.max_value is not None:
                if value > self.max_value:
                    errors.append(
                        f"{self.name}: value {value} is greater than maximum {self.max_value}"
                    )

        # Custom validation
        if self.validation is not None:
            try:
                if not self.validation(value):
                    errors.append(f"{self.name}: custom validation failed for value {value!r}")
            except Exception as e:
                errors.append(f"{self.name}: custom validation raised exception: {e}")

        return errors


@dataclass(frozen=True)
class ParameterSchema:
    """Schema defining all parameters for a strategy template.

    Per architecture.mdc: Strategy configurations must be validated against
    explicit schemas. This class provides validation for entire configurations.

    Attributes:
        parameters: Dictionary mapping parameter name to ParameterDefinition
    """

    parameters: dict[str, ParameterDefinition]

    def __post_init__(self) -> None:
        """Validate ParameterSchema itself."""
        if not self.parameters:
            raise ValueError("ParameterSchema must have at least one parameter")

        # Check for duplicate parameter names (shouldn't happen with dict, but validate)
        names = list(self.parameters.keys())
        if len(names) != len(set(names)):
            raise ValueError("ParameterSchema has duplicate parameter names")

    def validate(self, config: dict[str, Any]) -> list[str]:
        """Validate a configuration dictionary against this schema.

        Args:
            config: Configuration dictionary to validate

        Returns:
            List of error messages (empty if valid)

        Note:
            This is a pure function (no side effects, deterministic).
            Per architecture.mdc: Validation must happen at boundaries.
        """
        errors: list[str] = []

        # Check for unknown parameters
        unknown_params = set(config.keys()) - set(self.parameters.keys())
        if unknown_params:
            errors.append(
                f"Unknown parameters: {', '.join(sorted(unknown_params))}. "
                f"Valid parameters: {', '.join(sorted(self.parameters.keys()))}"
            )

        # Validate each parameter
        for param_name, param_def in self.parameters.items():
            if param_name not in config:
                if param_def.required:
                    errors.append(f"{param_name}: required parameter missing")
                # If not required, use default (validation happens when default is used)
                continue

            value = config[param_name]
            param_errors = param_def.validate_value(value)
            errors.extend(param_errors)

        return errors

    def apply_defaults(self, config: dict[str, Any]) -> dict[str, Any]:
        """Apply default values to configuration.

        Creates a new dictionary with defaults applied for missing optional parameters.

        Args:
            config: Configuration dictionary (may be missing optional parameters)

        Returns:
            New dictionary with defaults applied

        Note:
            This is a pure function (no side effects, deterministic).
        """
        result = dict(config)

        for param_name, param_def in self.parameters.items():
            if param_name not in result and not param_def.required:
                if param_def.default is not None:
                    result[param_name] = param_def.default

        return result

    def get_required_parameters(self) -> list[str]:
        """Get list of required parameter names.

        Returns:
            List of parameter names that are required
        """
        return [name for name, defn in self.parameters.items() if defn.required]
