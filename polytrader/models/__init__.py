# ITradingModel removed in Commit 3 (replaced by IStrategy in polytrader.strategies)
# Keeping create_model_factory and SimpleThresholdModel for temporary compatibility
# Will be removed in Commit 4 when SimpleThresholdStrategy is implemented
from polytrader.models.protocol import create_model_factory
from polytrader.models.simple_threshold import SimpleThresholdModel

__all__ = ["SimpleThresholdModel", "create_model_factory"]
