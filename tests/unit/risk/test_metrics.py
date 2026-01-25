"""Tests for risk metrics per observability.mdc §4."""

from unittest.mock import MagicMock

from polytrader.obs.metrics import (
    MemoryMetricsCollector,
    get_metrics_collector,
    record_projected_exposure,
    record_risk_check,
    record_risk_denial,
    set_metrics_collector,
)
from polytrader.risk.models import RiskReasonCode


class TestMemoryMetricsCollector:
    """Tests for MemoryMetricsCollector."""

    def test_increment_counter(self) -> None:
        """Test that counter increments correctly."""
        collector = MemoryMetricsCollector()

        collector.increment_counter("test_counter")
        assert collector.get_counter("test_counter") == 1

        collector.increment_counter("test_counter")
        assert collector.get_counter("test_counter") == 2

    def test_increment_counter_with_labels(self) -> None:
        """Test that counter increments with labels."""
        collector = MemoryMetricsCollector()

        collector.increment_counter("test_counter", labels={"label1": "value1"})
        assert collector.get_counter("test_counter", labels={"label1": "value1"}) == 1

        collector.increment_counter("test_counter", labels={"label1": "value2"})
        assert collector.get_counter("test_counter", labels={"label1": "value1"}) == 1
        assert collector.get_counter("test_counter", labels={"label1": "value2"}) == 1

    def test_set_gauge(self) -> None:
        """Test that gauge sets correctly."""
        collector = MemoryMetricsCollector()

        collector.set_gauge("test_gauge", 10.5)
        assert collector.get_gauge("test_gauge") == 10.5

        collector.set_gauge("test_gauge", 20.0)
        assert collector.get_gauge("test_gauge") == 20.0

    def test_set_gauge_with_labels(self) -> None:
        """Test that gauge sets with labels."""
        collector = MemoryMetricsCollector()

        collector.set_gauge("test_gauge", 10.5, labels={"label1": "value1"})
        assert collector.get_gauge("test_gauge", labels={"label1": "value1"}) == 10.5

        collector.set_gauge("test_gauge", 20.0, labels={"label1": "value2"})
        assert collector.get_gauge("test_gauge", labels={"label1": "value1"}) == 10.5
        assert collector.get_gauge("test_gauge", labels={"label1": "value2"}) == 20.0

    def test_get_all_metrics(self) -> None:
        """Test that get_all_metrics returns all metrics."""
        collector = MemoryMetricsCollector()

        collector.increment_counter("counter1")
        collector.increment_counter("counter2", labels={"label": "value"})
        collector.set_gauge("gauge1", 10.0)
        collector.set_gauge("gauge2", 20.0, labels={"label": "value"})

        all_metrics = collector.get_all_metrics()

        assert "counters" in all_metrics
        assert "gauges" in all_metrics
        assert "counter1" in all_metrics["counters"]
        assert "counter2" in all_metrics["counters"]
        assert "gauge1" in all_metrics["gauges"]
        assert "gauge2" in all_metrics["gauges"]

        # Verify structure (list of dicts with labels and value)
        assert isinstance(all_metrics["counters"]["counter1"], list)
        assert len(all_metrics["counters"]["counter1"]) == 1
        assert all_metrics["counters"]["counter1"][0]["value"] == 1
        assert all_metrics["counters"]["counter1"][0]["labels"] == {}


class TestMetricsCollectorSingleton:
    """Tests for global metrics collector singleton."""

    def test_get_metrics_collector_returns_singleton(self) -> None:
        """Test that get_metrics_collector returns singleton instance."""
        collector1 = get_metrics_collector()
        collector2 = get_metrics_collector()

        assert collector1 is collector2

    def test_set_metrics_collector_for_testing(self) -> None:
        """Test that set_metrics_collector allows injection for testing."""
        mock_collector = MagicMock(spec=MemoryMetricsCollector)

        set_metrics_collector(mock_collector)
        collector = get_metrics_collector()

        assert collector is mock_collector

        # Reset to default (now PrometheusMetricsCollector)
        set_metrics_collector(None)
        collector2 = get_metrics_collector()
        assert collector2 is not mock_collector
        # Default is now PrometheusMetricsCollector
        from polytrader.obs.metrics_prometheus import PrometheusMetricsCollector

        assert isinstance(collector2, PrometheusMetricsCollector)


class TestRiskMetrics:
    """Tests for risk metrics functions per observability.mdc §4."""

    def test_record_risk_check_allowed(self) -> None:
        """Test that record_risk_check records allowed checks."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_risk_check(allowed=True)

        assert collector.get_counter("risk_checks_total", labels={"allowed": "true"}) == 1
        assert collector.get_counter("risk_checks_total", labels={"allowed": "false"}) == 0

    def test_record_risk_check_denied(self) -> None:
        """Test that record_risk_check records denied checks."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_risk_check(allowed=False)

        assert collector.get_counter("risk_checks_total", labels={"allowed": "false"}) == 1
        assert collector.get_counter("risk_checks_total", labels={"allowed": "true"}) == 0

    def test_record_risk_denial(self) -> None:
        """Test that record_risk_denial records denial reasons."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_risk_denial(reason=RiskReasonCode.RISK_MAX_POSITION.value)
        record_risk_denial(reason=RiskReasonCode.RISK_MAX_POSITION.value)
        record_risk_denial(reason=RiskReasonCode.RISK_ORDER_TOO_LARGE.value)

        assert (
            collector.get_counter(
                "risk_denials_total", labels={"reason": RiskReasonCode.RISK_MAX_POSITION.value}
            )
            == 2
        )
        assert (
            collector.get_counter(
                "risk_denials_total", labels={"reason": RiskReasonCode.RISK_ORDER_TOO_LARGE.value}
            )
            == 1
        )

    def test_record_projected_exposure(self) -> None:
        """Test that record_projected_exposure records exposure gauge."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_projected_exposure(exposure=100.0)
        assert collector.get_gauge("risk_projected_exposure") == 100.0

        record_projected_exposure(exposure=200.0)
        assert collector.get_gauge("risk_projected_exposure") == 200.0

    def test_record_risk_check_multiple(self) -> None:
        """Test that multiple risk checks are recorded correctly."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_risk_check(allowed=True)
        record_risk_check(allowed=True)
        record_risk_check(allowed=False)
        record_risk_check(allowed=True)

        assert collector.get_counter("risk_checks_total", labels={"allowed": "true"}) == 3
        assert collector.get_counter("risk_checks_total", labels={"allowed": "false"}) == 1

    def test_record_risk_denial_multiple_reasons(self) -> None:
        """Test that multiple denial reasons are recorded separately."""
        collector = MemoryMetricsCollector()
        set_metrics_collector(collector)

        record_risk_denial(reason=RiskReasonCode.RISK_MAX_POSITION.value)
        record_risk_denial(reason=RiskReasonCode.RISK_ORDER_TOO_LARGE.value)
        record_risk_denial(reason=RiskReasonCode.RISK_MAX_POSITION.value)
        record_risk_denial(reason=RiskReasonCode.RISK_DATA_STALE.value)

        assert (
            collector.get_counter(
                "risk_denials_total", labels={"reason": RiskReasonCode.RISK_MAX_POSITION.value}
            )
            == 2
        )
        assert (
            collector.get_counter(
                "risk_denials_total", labels={"reason": RiskReasonCode.RISK_ORDER_TOO_LARGE.value}
            )
            == 1
        )
        assert (
            collector.get_counter(
                "risk_denials_total", labels={"reason": RiskReasonCode.RISK_DATA_STALE.value}
            )
            == 1
        )
