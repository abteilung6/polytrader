"""Shared fixtures for Risk unit tests."""

import pytest

from tests.factories.risk import create_risk_engine, create_risk_limits


@pytest.fixture
def default_risk_limits():
    """Create default risk limits for testing."""
    return create_risk_limits()


@pytest.fixture
def risk_engine(default_risk_limits, mock_clock):
    """Create RiskEngine for testing."""
    return create_risk_engine(limits=default_risk_limits, clock=mock_clock)
