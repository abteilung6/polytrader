"""Parameter schema for simple threshold strategy.

Per architecture.mdc: All strategy parameters must have explicit schemas
for validation and API documentation.
"""

from polytrader.strategies.schema import ParameterDefinition, ParameterSchema

SIMPLE_THRESHOLD_SCHEMA = ParameterSchema(
    parameters={
        "buy_threshold": ParameterDefinition(
            name="buy_threshold",
            type=float,
            required=False,  # Has default value
            default=0.30,
            description="Price threshold for BUY signals (0.0 to 1.0)",
            validation=None,  # min_value/max_value provide validation
            min_value=0.0,
            max_value=1.0,
        ),
        "min_history": ParameterDefinition(
            name="min_history",
            type=int,
            required=False,  # Has default value
            default=30,
            description="Minimum history ticks required before generating signals",
            validation=None,  # min_value provides validation
            min_value=0,
        ),
    }
)
