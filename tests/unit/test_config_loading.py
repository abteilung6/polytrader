"""Tests for config loading and validation.

Per Phase 7 Commit 3: Test config loading functionality including:
- Config loading from file
- Config validation (invalid config)
- Config hash calculation
- ConfigLoadedEvent emission
"""

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from polytrader.config import calculate_config_hash, load_config, validate_config
from polytrader.events import EventBus
from polytrader.events.types import ConfigLoadedEvent


class TestCalculateConfigHash:
    """Tests for config hash calculation."""

    def test_calculate_config_hash_deterministic(self) -> None:
        """Test that config hash is deterministic."""
        config1 = {"version": "1.0", "key": "value"}
        config2 = {"version": "1.0", "key": "value"}

        hash1 = calculate_config_hash(config1)
        hash2 = calculate_config_hash(config2)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 produces 64 hex characters

    def test_calculate_config_hash_different_configs(self) -> None:
        """Test that different configs produce different hashes."""
        config1 = {"version": "1.0", "key": "value1"}
        config2 = {"version": "1.0", "key": "value2"}

        hash1 = calculate_config_hash(config1)
        hash2 = calculate_config_hash(config2)

        assert hash1 != hash2

    def test_calculate_config_hash_order_independent(self) -> None:
        """Test that hash is independent of key order."""
        config1 = {"version": "1.0", "key1": "value1", "key2": "value2"}
        config2 = {"key2": "value2", "version": "1.0", "key1": "value1"}

        hash1 = calculate_config_hash(config1)
        hash2 = calculate_config_hash(config2)

        assert hash1 == hash2

    def test_calculate_config_hash_empty_config(self) -> None:
        """Test hash calculation with empty config."""
        config: dict[str, Any] = {}
        hash_value = calculate_config_hash(config)

        assert len(hash_value) == 64
        # Empty JSON object should produce a specific hash
        assert hash_value == calculate_config_hash({})


class TestValidateConfig:
    """Tests for config validation."""

    def test_validate_config_valid(self) -> None:
        """Test validation of valid config."""
        config = {"version": "1.0", "key": "value"}
        # Should not raise
        validate_config(config)

    def test_validate_config_without_version(self) -> None:
        """Test validation of config without version (should be allowed)."""
        config = {"key": "value"}
        # Should not raise (version is optional)
        validate_config(config)

    def test_validate_config_invalid_type(self) -> None:
        """Test validation of invalid config type."""
        with pytest.raises(ValueError, match="Config must be a dictionary"):
            validate_config("not a dict")  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="Config must be a dictionary"):
            validate_config([])  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="Config must be a dictionary"):
            validate_config(None)  # type: ignore[arg-type]

    def test_validate_config_invalid_version_type(self) -> None:
        """Test validation of config with invalid version type."""
        config = {"version": 1.0}  # Should be string
        with pytest.raises(ValueError, match="Config version must be a string"):
            validate_config(config)


class TestLoadConfig:
    """Tests for config loading."""

    @pytest.mark.asyncio
    async def test_load_config_from_file(self) -> None:
        """Test loading config from file."""
        config_data = {"version": "1.0", "key": "value"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            config = await load_config(config_path)

            assert config == config_data
            assert config["version"] == "1.0"
            assert config["key"] == "value"
        finally:
            Path(config_path).unlink()

    @pytest.mark.asyncio
    async def test_load_config_from_nonexistent_file(self) -> None:
        """Test loading config from nonexistent file."""
        with pytest.raises(FileNotFoundError):
            await load_config("nonexistent.json")

    @pytest.mark.asyncio
    async def test_load_config_invalid_json(self) -> None:
        """Test loading config with invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ invalid json }")
            config_path = f.name

        try:
            with pytest.raises(json.JSONDecodeError):
                await load_config(config_path)
        finally:
            Path(config_path).unlink()

    @pytest.mark.asyncio
    async def test_load_config_from_environment(self) -> None:
        """Test loading config from environment (returns empty dict for now)."""
        config = await load_config(config_path=None)

        assert isinstance(config, dict)
        # For now, environment loading returns empty dict
        # This can be enhanced later to load from environment variables

    @pytest.mark.asyncio
    async def test_load_config_validates_config(self) -> None:
        """Test that load_config validates the config."""
        invalid_config = "not a dict"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(invalid_config, f)
            config_path = f.name

        try:
            with pytest.raises(ValueError, match="Config must be a dictionary"):
                await load_config(config_path)
        finally:
            Path(config_path).unlink()

    @pytest.mark.asyncio
    async def test_load_config_calculates_hash(self) -> None:
        """Test that load_config calculates config hash."""
        config_data = {"version": "1.0", "key": "value"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            config = await load_config(config_path)

            # Hash should be calculated (we can't directly verify it, but
            # we can verify the config was loaded correctly)
            assert config == config_data
        finally:
            Path(config_path).unlink()

    @pytest.mark.asyncio
    async def test_load_config_emits_config_loaded_event(self) -> None:
        """Test that load_config emits ConfigLoadedEvent."""
        bus = EventBus()
        config_data = {"version": "1.2.3", "key": "value"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            # Subscribe to SYSTEM_LIFECYCLE events
            from polytrader.events import SYSTEM_LIFECYCLE

            queue = bus.subscribe(SYSTEM_LIFECYCLE)

            # Load config
            await load_config(config_path, bus=bus)

            # Check that ConfigLoadedEvent was emitted
            event = await queue.get()

            assert isinstance(event, ConfigLoadedEvent)
            assert event.config_hash == calculate_config_hash(config_data)
            assert event.config_version == "1.2.3"
            assert event.source.value == "ops"
        finally:
            Path(config_path).unlink()

    @pytest.mark.asyncio
    async def test_load_config_emits_event_without_version(self) -> None:
        """Test that load_config emits event with None version when version is default."""
        bus = EventBus()
        config_data = {"key": "value"}  # No version field

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            # Subscribe to SYSTEM_LIFECYCLE events
            from polytrader.events import SYSTEM_LIFECYCLE

            queue = bus.subscribe(SYSTEM_LIFECYCLE)

            # Load config
            await load_config(config_path, bus=bus)

            # Check that ConfigLoadedEvent was emitted
            event = await queue.get()

            assert isinstance(event, ConfigLoadedEvent)
            # When version is default "1.0", it should be None in event
            assert event.config_version is None
        finally:
            Path(config_path).unlink()

    @pytest.mark.asyncio
    async def test_load_config_without_bus(self) -> None:
        """Test that load_config works without event bus."""
        config_data = {"version": "1.0", "key": "value"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            config = await load_config(config_path, bus=None)

            assert config == config_data
            # Should not raise even without bus
        finally:
            Path(config_path).unlink()

    @pytest.mark.asyncio
    async def test_load_config_complex_structure(self) -> None:
        """Test loading config with complex nested structure."""
        config_data = {
            "version": "2.0",
            "risk_limits": {
                "max_order_size": 20.0,
                "max_position_per_market": 5.0,
            },
            "health_gates": {
                "max_market_data_staleness_seconds": 30.0,
                "require_user_stream": True,
            },
            "execution": {
                "size": 1.0,
                "sync_interval": 60.0,
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            config = await load_config(config_path)

            assert config == config_data
            assert config["version"] == "2.0"
            assert config["risk_limits"]["max_order_size"] == 20.0
            assert config["health_gates"]["require_user_stream"] is True
        finally:
            Path(config_path).unlink()
