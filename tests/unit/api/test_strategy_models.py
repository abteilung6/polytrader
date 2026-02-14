"""Unit tests for strategy API models.

Per Commit 14: API models for strategy templates, version selectors,
lifecycle states, and reproducibility metadata.

Per testing.mdc: Unit tests must be deterministic, fast, and isolated.
API model tests verify validation, serialization, and deserialization.
"""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from polytrader.api.models import (
    CreateStrategyRequest,
    RunIdentityResponse,
    StrategyLifecycleState,
    StrategyResponse,
    StrategyTypeResponse,
    StrategyTypesResponse,
    UpdateStrategyRequest,
    VersionSelectorRequest,
)


class TestVersionSelectorRequest:
    """Tests for VersionSelectorRequest model."""

    def test_exact_version(self) -> None:
        """Test VersionSelectorRequest with exact version."""
        request = VersionSelectorRequest(exact="1.2.3")

        assert request.exact == "1.2.3"
        assert request.channel is None
        assert request.major is None

    def test_channel_selector(self) -> None:
        """Test VersionSelectorRequest with channel selector."""
        request = VersionSelectorRequest(channel="stable", major=1)

        assert request.exact is None
        assert request.channel == "stable"
        assert request.major == 1

    def test_channel_without_major(self) -> None:
        """Test VersionSelectorRequest with channel but no major version."""
        request = VersionSelectorRequest(channel="beta")

        assert request.exact is None
        assert request.channel == "beta"
        assert request.major is None

    def test_invalid_channel(self) -> None:
        """Test that invalid channel raises ValidationError."""
        with pytest.raises(ValidationError):
            # Pydantic validates at runtime, so mypy doesn't catch invalid Literal values
            VersionSelectorRequest(channel="invalid")

    def test_both_exact_and_channel_raises_error(self) -> None:
        """Test that both exact and channel cannot be specified."""
        with pytest.raises(ValidationError):
            VersionSelectorRequest(exact="1.2.3", channel="stable")

    def test_neither_exact_nor_channel_raises_error(self) -> None:
        """Test that at least one of exact or channel must be specified."""
        with pytest.raises(ValidationError):
            VersionSelectorRequest()

    def test_major_without_channel_raises_error(self) -> None:
        """Test that major cannot be specified without channel."""
        with pytest.raises(ValidationError):
            VersionSelectorRequest(exact="1.2.3", major=1)


class TestRunIdentityResponse:
    """Tests for RunIdentityResponse model."""

    def test_run_identity_with_all_fields(self) -> None:
        """Test RunIdentityResponse with all fields."""
        response = RunIdentityResponse(
            template_code_ref="abc123",
            config_hash="a" * 64,  # SHA256 hash length
            dependency_set={"polytrader": "1.0.0", "numpy": "1.24.0"},
            market_data_snapshot_ref="snapshot_123",
        )

        assert response.template_code_ref == "abc123"
        assert response.config_hash == "a" * 64
        assert response.dependency_set == {"polytrader": "1.0.0", "numpy": "1.24.0"}
        assert response.market_data_snapshot_ref == "snapshot_123"

    def test_run_identity_with_optional_fields_none(self) -> None:
        """Test RunIdentityResponse with optional fields as None."""
        response = RunIdentityResponse(config_hash="a" * 64)

        assert response.template_code_ref is None
        assert response.config_hash == "a" * 64
        assert response.dependency_set is None
        assert response.market_data_snapshot_ref is None

    def test_run_identity_config_hash_required(self) -> None:
        """Test that config_hash is required."""
        with pytest.raises(ValidationError) as exc_info:
            RunIdentityResponse()  # type: ignore[call-arg]

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("config_hash",) for error in errors)


class TestStrategyTypeResponse:
    """Tests for StrategyTypeResponse model."""

    def test_strategy_type_response(self) -> None:
        """Test StrategyTypeResponse with all fields."""
        response = StrategyTypeResponse(
            type_id="simple_threshold",
            name="Simple Threshold Strategy",
            description="Generates BUY signals when price is below threshold",
            available_versions=["1.0.0", "1.1.0"],
            parameter_schema={"type": "object", "properties": {}},
        )

        assert response.type_id == "simple_threshold"
        assert response.name == "Simple Threshold Strategy"
        assert response.description == "Generates BUY signals when price is below threshold"
        assert response.available_versions == ["1.0.0", "1.1.0"]
        assert response.parameter_schema == {"type": "object", "properties": {}}

    def test_strategy_types_response(self) -> None:
        """Test StrategyTypesResponse with multiple types."""
        type1 = StrategyTypeResponse(
            type_id="simple_threshold",
            name="Simple Threshold",
            description="Description 1",
            available_versions=["1.0.0"],
            parameter_schema={},
        )
        type2 = StrategyTypeResponse(
            type_id="winner_threshold",
            name="Winner Threshold",
            description="Description 2",
            available_versions=["1.0.0"],
            parameter_schema={},
        )

        response = StrategyTypesResponse(types=[type1, type2])

        assert len(response.types) == 2
        assert response.types[0].type_id == "simple_threshold"
        assert response.types[1].type_id == "winner_threshold"


class TestCreateStrategyRequest:
    """Tests for CreateStrategyRequest model."""

    def test_create_strategy_request_with_all_fields(self) -> None:
        """Test CreateStrategyRequest with all fields."""
        request = CreateStrategyRequest(
            strategy_id="test_strategy",
            name="Test Strategy",
            description="A test strategy",
            config={"buy_threshold": 0.3},
            template_type_id="simple_threshold",
            version_selector=VersionSelectorRequest(exact="1.0.0"),
            desired_state="RUNNING",
        )

        assert request.strategy_id == "test_strategy"
        assert request.name == "Test Strategy"
        assert request.description == "A test strategy"
        assert request.config == {"buy_threshold": 0.3}
        assert request.template_type_id == "simple_threshold"
        assert request.version_selector.exact == "1.0.0"
        assert request.desired_state == "RUNNING"

    def test_create_strategy_request_default_desired_state(self) -> None:
        """Test that desired_state defaults to STOPPED."""
        request = CreateStrategyRequest(
            strategy_id="test_strategy",
            name="Test Strategy",
            config={},
            template_type_id="simple_threshold",
            version_selector=VersionSelectorRequest(exact="1.0.0"),
        )

        assert request.desired_state == "STOPPED"

    def test_create_strategy_request_with_channel_selector(self) -> None:
        """Test CreateStrategyRequest with channel version selector."""
        request = CreateStrategyRequest(
            strategy_id="test_strategy",
            name="Test Strategy",
            config={},
            template_type_id="simple_threshold",
            version_selector=VersionSelectorRequest(channel="stable", major=1),
            desired_state="STOPPED",
        )

        assert request.version_selector.channel == "stable"
        assert request.version_selector.major == 1


class TestUpdateStrategyRequest:
    """Tests for UpdateStrategyRequest model."""

    def test_update_strategy_request_all_optional(self) -> None:
        """Test UpdateStrategyRequest with all fields optional."""
        request = UpdateStrategyRequest()

        assert request.name is None
        assert request.description is None
        assert request.config is None
        assert request.desired_state is None

    def test_update_strategy_request_with_desired_state(self) -> None:
        """Test UpdateStrategyRequest with desired_state."""
        request = UpdateStrategyRequest(desired_state="PAUSED")

        assert request.desired_state == "PAUSED"

    def test_update_strategy_request_with_all_fields(self) -> None:
        """Test UpdateStrategyRequest with all fields."""
        request = UpdateStrategyRequest(
            name="Updated Name",
            description="Updated description",
            config={"buy_threshold": 0.4},
            desired_state="RUNNING",
        )

        assert request.name == "Updated Name"
        assert request.description == "Updated description"
        assert request.config == {"buy_threshold": 0.4}
        assert request.desired_state == "RUNNING"


class TestStrategyResponse:
    """Tests for StrategyResponse model."""

    def test_strategy_response_with_all_fields(self) -> None:
        """Test StrategyResponse with all fields."""
        deployment_id = str(uuid.uuid4())
        run_identity = RunIdentityResponse(
            template_code_ref="abc123",
            config_hash="a" * 64,
            dependency_set={"polytrader": "1.0.0"},
            market_data_snapshot_ref="snapshot_123",
        )

        response = StrategyResponse(
            strategy_id="test_strategy",
            name="Test Strategy",
            description="A test strategy",
            config={"buy_threshold": 0.3},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            desired_state="RUNNING",
            actual_state="RUNNING",
            last_transition_at=datetime.now(UTC),
            last_error=None,
            run_identity=run_identity,
            deployment_id=deployment_id,
            run_id="run_123",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            enabled=True,
        )

        assert response.strategy_id == "test_strategy"
        assert response.name == "Test Strategy"
        assert response.template_type_id == "simple_threshold"
        assert response.template_version == "1.0.0"
        assert response.desired_state == "RUNNING"
        assert response.actual_state == "RUNNING"
        assert response.run_identity == run_identity
        assert response.deployment_id == deployment_id
        assert response.run_id == "run_123"
        assert response.enabled is True  # Activation for live (distinct from lifecycle)

    def test_strategy_response_enabled_is_activation_for_live(self) -> None:
        """enabled = in active live list (Mode), not lifecycle."""
        response_live = StrategyResponse(
            strategy_id="test_strategy",
            name="Test Strategy",
            config={},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            desired_state="RUNNING",
            actual_state="RUNNING",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            enabled=True,
        )
        assert response_live.enabled is True

        response_paper = StrategyResponse(
            strategy_id="test_strategy",
            name="Test Strategy",
            config={},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            desired_state="RUNNING",
            actual_state="RUNNING",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            enabled=False,
        )
        assert response_paper.enabled is False

    def test_strategy_response_with_optional_fields_none(self) -> None:
        """Test StrategyResponse with optional fields as None."""
        response = StrategyResponse(
            strategy_id="test_strategy",
            name="Test Strategy",
            config={},
            template_type_id="simple_threshold",
            template_version="1.0.0",
            desired_state="STOPPED",
            actual_state="STOPPED",
            enabled=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        assert response.description is None
        assert response.last_transition_at is None
        assert response.last_error is None
        assert response.run_identity is None
        assert response.deployment_id is None
        assert response.run_id is None

    def test_strategy_response_validates_lifecycle_states(self) -> None:
        """Test that StrategyResponse validates lifecycle state values."""
        # Valid states should work
        valid_states: list[StrategyLifecycleState] = [
            "STOPPED",
            "STARTING",
            "RUNNING",
            "PAUSED",
            "DRAINING",
            "STOPPING",
            "ERROR",
        ]

        for state in valid_states:
            response = StrategyResponse(
                strategy_id="test_strategy",
                name="Test Strategy",
                config={},
                template_type_id="simple_threshold",
                template_version="1.0.0",
                desired_state=state,
                actual_state=state,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                enabled=False,
            )

            assert response.desired_state == state
            assert response.actual_state == state

        # Invalid state should raise ValidationError
        with pytest.raises(ValidationError):
            StrategyResponse(
                strategy_id="test_strategy",
                name="Test Strategy",
                config={},
                template_type_id="simple_threshold",
                template_version="1.0.0",
                desired_state="INVALID",
                actual_state="STOPPED",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                enabled=False,
            )
