"""Tests for common ID utilities."""

import uuid

from polytrader.common.ids import (
    generate_correlation_id,
    get_run_id,
    reset_run_id,
)


class TestRunID:
    """Tests for run_id generation."""

    def test_get_run_id_returns_singleton(self) -> None:
        """Test that get_run_id returns the same ID for the process."""
        reset_run_id()  # Start fresh

        run_id_1 = get_run_id()
        run_id_2 = get_run_id()

        assert run_id_1 == run_id_2
        assert isinstance(run_id_1, str)
        assert len(run_id_1) == 36  # UUID format

    def test_get_run_id_different_after_reset(self) -> None:
        """Test that reset_run_id allows generating a new run_id."""
        reset_run_id()
        run_id_1 = get_run_id()

        reset_run_id()
        run_id_2 = get_run_id()

        assert run_id_1 != run_id_2

    def test_get_run_id_format(self) -> None:
        """Test that run_id is a valid UUID format."""
        reset_run_id()
        run_id = get_run_id()

        # Should be a valid UUID string
        uuid.UUID(run_id)  # Will raise if invalid


class TestCorrelationID:
    """Tests for correlation_id generation."""

    def test_generate_correlation_id_returns_unique_ids(self) -> None:
        """Test that each call generates a unique correlation ID."""
        id_1 = generate_correlation_id()
        id_2 = generate_correlation_id()

        assert id_1 != id_2
        assert isinstance(id_1, str)
        assert isinstance(id_2, str)
        assert len(id_1) == 36  # UUID format
        assert len(id_2) == 36

    def test_generate_correlation_id_format(self) -> None:
        """Test that correlation_id is a valid UUID format."""
        correlation_id = generate_correlation_id()

        # Should be a valid UUID string
        uuid.UUID(correlation_id)  # Will raise if invalid

    def test_generate_correlation_id_multiple_calls(self) -> None:
        """Test that multiple calls generate different IDs."""
        ids = {generate_correlation_id() for _ in range(100)}

        # All should be unique
        assert len(ids) == 100


class TestResetRunID:
    """Tests for reset_run_id function."""

    def test_reset_run_id_clears_global_state(self) -> None:
        """Test that reset_run_id clears the global run_id."""
        reset_run_id()
        run_id_before = get_run_id()

        reset_run_id()
        run_id_after = get_run_id()

        assert run_id_before != run_id_after

    def test_reset_run_id_allows_new_run_id(self) -> None:
        """Test that after reset, a new run_id can be generated."""
        reset_run_id()
        first_run_id = get_run_id()

        reset_run_id()
        second_run_id = get_run_id()

        # Both should be valid UUIDs but different
        assert first_run_id != second_run_id
        uuid.UUID(first_run_id)
        uuid.UUID(second_run_id)
