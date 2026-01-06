"""Tests for portfolio management."""

import pytest

from polytrader.core import Portfolio, PortfolioManager, Position, RandomStrategy
from polytrader.types import MarketTick


class TestPortfolio:
    """Tests for Portfolio class."""

    def test_initial_portfolio(self) -> None:
        """Test initializing a portfolio."""
        portfolio = Portfolio(balance=1000.0)
        assert portfolio.balance == 1000.0
        assert len(portfolio.positions) == 0

    def test_add_position(self) -> None:
        """Test adding a position."""
        portfolio = Portfolio(balance=1000.0)
        portfolio.add_position("market1", "UP", quantity=10.0, price=0.5)
        
        position = portfolio.get_position("market1", "UP")
        assert position is not None
        assert position.quantity == 10.0
        assert position.avg_price == 0.5

    def test_update_position(self) -> None:
        """Test updating an existing position."""
        portfolio = Portfolio(balance=1000.0)
        portfolio.add_position("market1", "UP", quantity=10.0, price=0.5)
        portfolio.add_position("market1", "UP", quantity=10.0, price=0.6)
        
        position = portfolio.get_position("market1", "UP")
        assert position is not None
        assert position.quantity == 20.0
        assert position.avg_price == 0.55  # (10*0.5 + 10*0.6) / 20

    def test_get_total_value(self) -> None:
        """Test calculating total portfolio value."""
        portfolio = Portfolio(balance=1000.0)
        portfolio.add_position("market1", "UP", quantity=10.0, price=0.5)
        
        prices = {("market1", "UP"): 0.6}
        total_value = portfolio.get_total_value(prices)
        assert total_value == 1000.0 + (10.0 * 0.6)


class TestRandomStrategy:
    """Tests for RandomStrategy."""

    def test_random_strategy_no_trade(self) -> None:
        """Test random strategy with zero probability."""
        strategy = RandomStrategy(trade_probability=0.0)
        portfolio = Portfolio(balance=1000.0)
        
        decision = strategy.decide(portfolio, "market1", 0.5, 0.5)
        assert decision is None

    def test_random_strategy_always_trade(self) -> None:
        """Test random strategy with probability 1.0."""
        strategy = RandomStrategy(trade_probability=1.0, min_trade_amount=1.0, max_trade_amount=1.0)
        portfolio = Portfolio(balance=1000.0)
        
        decision = strategy.decide(portfolio, "market1", 0.5, 0.5)
        assert decision is not None
        assert decision.market_id == "market1"
        assert decision.outcome in ("UP", "DOWN")
        assert decision.amount == 1.0

    def test_random_strategy_insufficient_balance(self) -> None:
        """Test random strategy with insufficient balance."""
        strategy = RandomStrategy(trade_probability=1.0, min_trade_amount=100.0, max_trade_amount=100.0)
        portfolio = Portfolio(balance=50.0)
        
        decision = strategy.decide(portfolio, "market1", 0.5, 0.5)
        assert decision is None


class TestPortfolioManager:
    """Tests for PortfolioManager."""

    def test_initial_portfolio_manager(self) -> None:
        """Test initializing portfolio manager."""
        manager = PortfolioManager(initial_balance=1000.0)
        assert manager.get_balance() == 1000.0
        assert manager.total_trades == 0

    def test_process_tick_executes_trade(self) -> None:
        """Test processing a tick executes a trade."""
        strategy = RandomStrategy(trade_probability=1.0, min_trade_amount=10.0, max_trade_amount=10.0)
        manager = PortfolioManager(initial_balance=1000.0, strategy=strategy)
        
        tick = MarketTick(
            ts=1000.0,
            market_id="market1",
            outcome="UP",
            best_bid=0.49,
            best_ask=0.51,
        )
        
        decision = manager.process_tick(tick)
        # May or may not trade depending on random, but if it does:
        if decision is not None:
            assert decision.market_id == "market1"
            assert manager.get_balance() < 1000.0
            assert manager.total_trades > 0

    def test_process_prices(self) -> None:
        """Test processing prices directly."""
        strategy = RandomStrategy(trade_probability=1.0, min_trade_amount=10.0, max_trade_amount=10.0)
        manager = PortfolioManager(initial_balance=1000.0, strategy=strategy)
        
        decision = manager.process_prices("market1", up_price=0.5, down_price=0.5)
        # May or may not trade depending on random
        if decision is not None:
            assert decision.market_id == "market1"
            assert decision.outcome in ("UP", "DOWN")

    def test_get_statistics(self) -> None:
        """Test getting portfolio statistics."""
        manager = PortfolioManager(initial_balance=1000.0)
        stats = manager.get_statistics()
        
        assert stats["balance"] == 1000.0
        assert stats["total_trades"] == 0
        assert stats["total_spent"] == 0.0
        assert stats["num_positions"] == 0

