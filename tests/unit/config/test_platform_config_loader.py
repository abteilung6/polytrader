"""Tests for platform configuration YAML loader.

Per Commit 3 of PLATFORM_CONFIGURATION_PROPOSAL.md:
- YAML file loads and validates correctly
- Missing file, malformed YAML, invalid values produce clear errors
- ConfigLoadedEvent emitted with correct hash and version
- JSON fallback works (backward compatibility)
- Hash is deterministic and changes with config changes
"""

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from polytrader.config.loader import (
    calculate_platform_config_hash,
    config_to_dict,
    load_platform_config,
)
from polytrader.config.models import PlatformConfig
from polytrader.events import EventBus
from polytrader.events.types import ConfigLoadedEvent


class TestLoadPlatformConfigNoPath:
    """load_platform_config(None) returns all defaults."""

    @pytest.mark.asyncio
    async def test_no_path_returns_defaults(self) -> None:
        """No config path returns PlatformConfig with all defaults."""
        config = await load_platform_config(None)

        assert isinstance(config, PlatformConfig)
        assert config.version == "1.0"
        assert config.risk.max_order_size == 10.0
        assert config.api.port == 8000


class TestLoadPlatformConfigFromYaml:
    """Loading from YAML files."""

    @pytest.mark.asyncio
    async def test_from_yaml_file(self) -> None:
        """YAML file with overrides loads correctly."""
        yaml_data = {
            "version": "2.0",
            "risk": {"max_order_size": 5.0},
            "api": {"port": 9000},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_data, f)
            config_path = Path(f.name)

        try:
            config = await load_platform_config(config_path)

            assert config.version == "2.0"
            assert config.risk.max_order_size == 5.0
            assert config.api.port == 9000
            # Defaults preserved for unspecified fields
            assert config.risk.max_position_per_market == 1.0
            assert config.api.host == "0.0.0.0"
        finally:
            config_path.unlink()

    @pytest.mark.asyncio
    async def test_partial_yaml(self) -> None:
        """YAML with only one field override; all other defaults preserved."""
        yaml_data = {"risk": {"max_order_size": 5.0}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_data, f)
            config_path = Path(f.name)

        try:
            config = await load_platform_config(config_path)

            assert config.risk.max_order_size == 5.0
            assert config.version == "1.0"  # default
            assert config.risk.max_position_per_market == 1.0  # default
            assert config.health_gates.max_error_rate == 0.1  # default
        finally:
            config_path.unlink()

    @pytest.mark.asyncio
    async def test_empty_yaml(self) -> None:
        """Empty YAML file returns all defaults."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            config_path = Path(f.name)

        try:
            config = await load_platform_config(config_path)
            assert config.risk.max_order_size == 10.0
        finally:
            config_path.unlink()

    @pytest.mark.asyncio
    async def test_yml_extension(self) -> None:
        """Files with .yml extension also load as YAML."""
        yaml_data = {"risk": {"max_order_size": 7.5}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump(yaml_data, f)
            config_path = Path(f.name)

        try:
            config = await load_platform_config(config_path)
            assert config.risk.max_order_size == 7.5
        finally:
            config_path.unlink()


class TestLoadPlatformConfigErrors:
    """Error cases produce clear, specific exceptions."""

    @pytest.mark.asyncio
    async def test_file_not_found(self) -> None:
        """Non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            await load_platform_config(Path("/nonexistent/path/config.yaml"))

    @pytest.mark.asyncio
    async def test_invalid_yaml(self) -> None:
        """Malformed YAML raises yaml.YAMLError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("{ invalid: yaml: : :\n  broken")
            config_path = Path(f.name)

        try:
            with pytest.raises(yaml.YAMLError):
                await load_platform_config(config_path)
        finally:
            config_path.unlink()

    @pytest.mark.asyncio
    async def test_invalid_values(self) -> None:
        """YAML with invalid values raises ValidationError."""
        from pydantic import ValidationError

        yaml_data = {"risk": {"max_order_size": -1.0}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_data, f)
            config_path = Path(f.name)

        try:
            with pytest.raises(ValidationError):
                await load_platform_config(config_path)
        finally:
            config_path.unlink()


class TestLoadPlatformConfigEvent:
    """ConfigLoadedEvent emission."""

    @pytest.mark.asyncio
    async def test_emits_config_loaded_event(self) -> None:
        """With bus, ConfigLoadedEvent is emitted with correct hash and version."""
        bus = EventBus()
        yaml_data = {"version": "2.5", "risk": {"max_order_size": 5.0}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_data, f)
            config_path = Path(f.name)

        try:
            from polytrader.events import SYSTEM_LIFECYCLE

            queue = bus.subscribe(SYSTEM_LIFECYCLE)

            config = await load_platform_config(config_path, bus=bus)
            event = await queue.get()

            assert isinstance(event, ConfigLoadedEvent)
            assert event.config_version == "2.5"
            assert event.config_hash == calculate_platform_config_hash(config)
            assert len(event.config_hash) == 64  # SHA256 hex
        finally:
            config_path.unlink()

    @pytest.mark.asyncio
    async def test_no_bus_no_error(self) -> None:
        """Without bus, no error and config is returned."""
        config = await load_platform_config(None, bus=None)
        assert isinstance(config, PlatformConfig)

    @pytest.mark.asyncio
    async def test_emits_event_for_defaults(self) -> None:
        """ConfigLoadedEvent emitted even with no config file (defaults)."""
        bus = EventBus()

        from polytrader.events import SYSTEM_LIFECYCLE

        queue = bus.subscribe(SYSTEM_LIFECYCLE)

        config = await load_platform_config(None, bus=bus)
        event = await queue.get()

        assert isinstance(event, ConfigLoadedEvent)
        assert event.config_version == "1.0"
        assert event.config_hash == calculate_platform_config_hash(config)


class TestPlatformConfigHash:
    """Hash calculation is deterministic and sensitive to changes."""

    def test_hash_deterministic(self) -> None:
        """Same config produces same hash."""
        config1 = PlatformConfig()
        config2 = PlatformConfig()

        hash1 = calculate_platform_config_hash(config1)
        hash2 = calculate_platform_config_hash(config2)

        assert hash1 == hash2
        assert len(hash1) == 64

    def test_hash_changes_on_different_values(self) -> None:
        """Different config produces different hash."""
        config1 = PlatformConfig()
        config2 = PlatformConfig.model_validate({"risk": {"max_order_size": 5.0}})

        hash1 = calculate_platform_config_hash(config1)
        hash2 = calculate_platform_config_hash(config2)

        assert hash1 != hash2

    def test_hash_changes_on_version(self) -> None:
        """Different version produces different hash."""
        config1 = PlatformConfig(version="1.0")
        config2 = PlatformConfig(version="2.0")

        assert calculate_platform_config_hash(config1) != calculate_platform_config_hash(config2)


class TestConfigToDict:
    """config_to_dict produces JSON-serializable dict."""

    def test_round_trip(self) -> None:
        """Dict can be JSON-serialized and deserialized."""
        config = PlatformConfig()
        data = config_to_dict(config)

        # Must be JSON-serializable
        json_str = json.dumps(data)
        assert isinstance(json_str, str)

        # Must round-trip
        restored = PlatformConfig.model_validate(json.loads(json_str))
        assert restored.risk.max_order_size == config.risk.max_order_size


class TestJsonFallback:
    """JSON config files load correctly (backward compatibility)."""

    @pytest.mark.asyncio
    async def test_json_file_loads(self) -> None:
        """JSON file with .json extension loads correctly."""
        json_data = {
            "version": "1.5",
            "risk": {"max_order_size": 3.0},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(json_data, f)
            config_path = Path(f.name)

        try:
            config = await load_platform_config(config_path)

            assert config.version == "1.5"
            assert config.risk.max_order_size == 3.0
        finally:
            config_path.unlink()

    @pytest.mark.asyncio
    async def test_invalid_json(self) -> None:
        """Malformed JSON raises JSONDecodeError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ invalid json }")
            config_path = Path(f.name)

        try:
            with pytest.raises(json.JSONDecodeError):
                await load_platform_config(config_path)
        finally:
            config_path.unlink()
