"""Platform configuration YAML loader.

Loads, validates, hashes, and emits ConfigLoadedEvent for platform configuration.

Usage:
    config = load_platform_config(Path("config/platform.paper.yaml"), bus=bus)
    config = load_platform_config(None)  # All safe defaults

Per trading.mdc §7: Config must be validated, versioned, and auditable.
Per observability.mdc §1: Config hash emitted as ConfigLoadedEvent.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from polytrader.config.models import PlatformConfig

if TYPE_CHECKING:
    from polytrader.events.bus import EventBus


def config_to_dict(config: PlatformConfig) -> dict[str, Any]:
    """Serialize PlatformConfig to a plain dict for hashing.

    Uses Pydantic's model_dump with mode="json" for JSON-safe types
    and sorted keys for deterministic output.

    Args:
        config: PlatformConfig instance.

    Returns:
        Plain dictionary representation.
    """
    return config.model_dump(mode="json")


def calculate_platform_config_hash(config: PlatformConfig) -> str:
    """Calculate deterministic SHA256 hash of a PlatformConfig.

    Per observability.mdc §1: Config hash is used for audit trail.

    Args:
        config: PlatformConfig instance.

    Returns:
        SHA256 hash as hexadecimal string (64 chars).
    """
    data = config_to_dict(config)
    canonical_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


async def load_platform_config(
    config_path: Path | None = None,
    bus: EventBus | None = None,
) -> PlatformConfig:
    """Load and validate platform configuration.

    If config_path is None, returns PlatformConfig() with all safe defaults.
    If config_path is provided, reads YAML (or JSON) and validates atomically
    via Pydantic. Emits ConfigLoadedEvent with hash and version.

    Args:
        config_path: Path to YAML (or JSON) config file. None for defaults.
        bus: Event bus for emitting ConfigLoadedEvent (optional).

    Returns:
        Validated, frozen PlatformConfig instance.

    Raises:
        FileNotFoundError: If config_path does not exist.
        yaml.YAMLError: If YAML is malformed.
        json.JSONDecodeError: If JSON file is malformed.
        pydantic.ValidationError: If config values fail validation.
    """
    if config_path is None:
        config = PlatformConfig()
    else:
        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, encoding="utf-8") as f:
            raw_text = f.read()

        # Determine format from extension (JSON fallback for backward compat)
        if config_path.suffix in (".json",):
            data = json.loads(raw_text)
        else:
            # Default to YAML (covers .yaml, .yml, and anything else)
            data = yaml.safe_load(raw_text)

        # yaml.safe_load returns None for empty files
        if data is None:
            data = {}

        # Pydantic validates all constraints atomically
        config = PlatformConfig.model_validate(data)

    # Calculate hash and emit event
    config_hash = calculate_platform_config_hash(config)

    if bus is not None:
        from polytrader.events import SYSTEM_LIFECYCLE
        from polytrader.events.types import ConfigLoadedEvent

        event = ConfigLoadedEvent(
            config_hash=config_hash,
            config_version=config.version,
        )
        await bus.publish(SYSTEM_LIFECYCLE, event)

    return config
