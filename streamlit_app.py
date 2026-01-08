#!/usr/bin/env python3
"""Streamlit app for visualizing backtest results with prices and trades."""

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from backtest import (
    extract_asset_from_market_id,
    find_all_data_files,
    load_ticks_from_csv,
)
from polytrader.core.manager import PortfolioManager
from polytrader.core.strategy_registry import create_strategy
from polytrader.types import MarketTick, Outcome


@dataclass
class TradeEvent:
    """Record of a trade execution."""

    timestamp: float
    outcome: str
    amount: float
    price: float
    shares: float
    balance: float
    up_price: float
    down_price: float


@dataclass
class PricePoint:
    """Price data point at a timestamp."""

    timestamp: float
    up_price: float
    down_price: float
    balance: float
    up_shares: float
    down_shares: float


def simulate_backtest_with_tracking(
    market_id: str,
    csv_files: list[str],
    strategy_name: str,
    initial_balance: float,
    timestamp_cutoff: float | None = None,
) -> tuple[list[PricePoint], list[TradeEvent]]:
    """Run backtest and track all price movements and trades.

    Returns:
        Tuple of (price_points, trade_events)
    """
    # Load all ticks
    all_ticks: list[MarketTick] = []
    for csv_file in csv_files:
        ticks = load_ticks_from_csv(csv_file)
        all_ticks.extend(ticks)

    if timestamp_cutoff is not None:
        all_ticks = [tick for tick in all_ticks if tick.ts >= timestamp_cutoff]

    if not all_ticks:
        return [], []

    all_ticks.sort(key=lambda t: t.ts)

    # Initialize portfolio manager
    strategy = create_strategy(strategy_name)
    portfolio_manager = PortfolioManager(
        initial_balance=initial_balance,
        strategy=strategy,
    )

    # Group ticks by timestamp
    tick_groups: dict[float, dict[Outcome, MarketTick]] = defaultdict(dict)
    for tick in all_ticks:
        rounded_ts = round(tick.ts, 1)
        tick_groups[rounded_ts][tick.outcome] = tick

    price_points: list[PricePoint] = []
    trade_events: list[TradeEvent] = []

    processed_timestamps = sorted(tick_groups.keys())
    latest_up_tick: MarketTick | None = None
    latest_down_tick: MarketTick | None = None

    for ts in processed_timestamps:
        group = tick_groups[ts]

        # Update latest ticks
        if "UP" in group:
            latest_up_tick = group["UP"]
        if "DOWN" in group:
            latest_down_tick = group["DOWN"]

        # Get current prices
        if latest_up_tick and latest_down_tick:
            # Check if timestamps match (within tolerance)
            timestamp_diff = abs(latest_up_tick.ts - latest_down_tick.ts)
            if timestamp_diff <= 0.1:
                up_price = latest_up_tick.best_ask
                down_price = latest_down_tick.best_ask

                # Get current positions
                up_pos = portfolio_manager.portfolio.get_position(market_id, "UP")
                down_pos = portfolio_manager.portfolio.get_position(market_id, "DOWN")

                up_shares = up_pos.quantity if up_pos else 0.0
                down_shares = down_pos.quantity if down_pos else 0.0
                balance = portfolio_manager.get_balance()

                # Record price point
                price_points.append(
                    PricePoint(
                        timestamp=ts,
                        up_price=up_price,
                        down_price=down_price,
                        balance=balance,
                        up_shares=up_shares,
                        down_shares=down_shares,
                    )
                )

                # Process trading decision
                decision = portfolio_manager.process_prices(
                    market_id=market_id,
                    up_price=up_price,
                    down_price=down_price,
                    timestamp=ts,
                )

                # Record trade if executed
                if decision:
                    trades = decision if isinstance(decision, list) else [decision]
                    balance_after = portfolio_manager.get_balance()

                    for trade in trades:
                        shares = trade.amount / trade.price if trade.price > 0 else 0
                        trade_events.append(
                            TradeEvent(
                                timestamp=ts,
                                outcome=trade.outcome,
                                amount=trade.amount,
                                price=trade.price,
                                shares=shares,
                                balance=balance_after,
                                up_price=up_price,
                                down_price=down_price,
                            )
                        )

    return price_points, trade_events


def main():
    """Main Streamlit app."""
    st.set_page_config(page_title="Polytrader Backtest Visualizer", layout="wide")

    st.title("📊 Polytrader Backtest Visualizer")
    st.markdown("Visualize market prices and trades from backtest results")

    # Sidebar for configuration
    with st.sidebar:
        st.header("Configuration")

        # Strategy selection
        strategy_name = st.selectbox(
            "Strategy",
            ["gabagool", "gabagool-v2", "gabagool-v3"],
            index=2,
        )

        # Initial balance
        initial_balance = st.number_input(
            "Initial Balance (USDC)",
            min_value=100.0,
            max_value=100000.0,
            value=1000.0,
            step=100.0,
        )

        # Data directory
        data_dir = st.text_input("Data Directory", value="data")

        # Load markets
        if st.button("Load Markets"):
            with st.spinner("Loading markets..."):
                markets = find_all_data_files(data_dir)
                if markets:
                    st.session_state.markets = markets
                    st.success(f"Loaded {len(markets)} markets")
                else:
                    st.error(f"No markets found in '{data_dir}'")

    # Market selection
    if "markets" not in st.session_state:
        st.info("👈 Click 'Load Markets' in the sidebar to get started")
        return

    markets = st.session_state.markets
    market_options = list(sorted(markets.keys()))

    selected_market = st.selectbox("Select Market", market_options)

    if not selected_market:
        return

    # Run backtest for selected market
    csv_files = markets[selected_market]
    st.info(f"📁 Found {len(csv_files)} data file(s) for market: {selected_market}")

    if st.button("🔄 Run Backtest"):
        with st.spinner("Running backtest..."):
            price_points, trade_events = simulate_backtest_with_tracking(
                market_id=selected_market,
                csv_files=csv_files,
                strategy_name=strategy_name,
                initial_balance=initial_balance,
            )

            if price_points:
                st.session_state.price_points = price_points
                st.session_state.trade_events = trade_events
                st.session_state.market_id = selected_market
                st.success(f"✅ Backtest complete! Found {len(trade_events)} trades")
            else:
                st.error("No price data found for this market")

    # Display visualizations
    if "price_points" not in st.session_state:
        return

    price_points = st.session_state.price_points
    trade_events = st.session_state.trade_events
    market_id = st.session_state.market_id

    st.header(f"📈 Market: {market_id}")
    st.markdown(f"**Asset:** {extract_asset_from_market_id(market_id).upper()}")

    # Convert to DataFrame for easier plotting
    df_prices = pd.DataFrame(
        [
            {
                "timestamp": pp.timestamp,
                "datetime": datetime.fromtimestamp(pp.timestamp),
                "up_price": pp.up_price,
                "down_price": pp.down_price,
                "balance": pp.balance,
                "up_shares": pp.up_shares,
                "down_shares": pp.down_shares,
            }
            for pp in price_points
        ]
    )

    # Price chart with trade markers
    st.subheader("💰 Prices Over Time (with Trade Markers)")
    
    # Create a combined chart showing prices and trades
    chart_data = df_prices[["datetime", "up_price", "down_price"]].copy()
    chart_data = chart_data.set_index("datetime")
    
    # Add trade markers as separate series
    if trade_events:
        trade_markers_up = pd.Series(index=chart_data.index, dtype=float)
        trade_markers_down = pd.Series(index=chart_data.index, dtype=float)
        
        for trade in trade_events:
            trade_dt = datetime.fromtimestamp(trade.timestamp)
            # Find closest timestamp
            if len(chart_data) > 0:
                closest_idx = chart_data.index.get_indexer([trade_dt], method="nearest")[0]
                if closest_idx >= 0 and closest_idx < len(chart_data):
                    closest_dt = chart_data.index[closest_idx]
                    if trade.outcome == "UP":
                        trade_markers_up.loc[closest_dt] = trade.price
                    else:
                        trade_markers_down.loc[closest_dt] = trade.price
        
        # Combine with main chart data
        chart_data["trade_up"] = trade_markers_up
        chart_data["trade_down"] = trade_markers_down
    
    st.line_chart(chart_data, use_container_width=True, height=400)
    
    # Legend explanation
    st.caption("📈 Blue = UP price | 🟢 Orange = DOWN price | 🔴 Red = UP trades | 🟣 Purple = DOWN trades")

    # Trade markers overlay
    if trade_events:
        st.subheader("🔔 Trade Events")
        df_trades = pd.DataFrame(
            [
                {
                    "timestamp": te.timestamp,
                    "datetime": datetime.fromtimestamp(te.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
                    "outcome": te.outcome,
                    "amount": te.amount,
                    "price": te.price,
                    "shares": te.shares,
                    "balance_after": te.balance,
                    "up_price": te.up_price,
                    "down_price": te.down_price,
                }
                for te in trade_events
            ]
        )

        # Display trade table
        st.dataframe(
            df_trades[
                ["datetime", "outcome", "amount", "price", "shares", "balance_after"]
            ].style.format(
                {
                    "amount": "${:.2f}",
                    "price": "${:.4f}",
                    "shares": "{:.4f}",
                    "balance_after": "${:.2f}",
                }
            ),
            use_container_width=True,
            height=400,
        )

        # Trade summary
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Trades", len(trade_events))
        with col2:
            total_spent = df_trades["amount"].sum()
            st.metric("Total Spent", f"${total_spent:.2f}")
        with col3:
            final_balance = df_trades["balance_after"].iloc[-1] if len(df_trades) > 0 else initial_balance
            st.metric("Final Balance", f"${final_balance:.2f}")
        with col4:
            profit = final_balance - initial_balance
            profit_pct = (profit / initial_balance * 100) if initial_balance > 0 else 0
            st.metric("Profit", f"${profit:+.2f} ({profit_pct:+.2f}%)")

    # Portfolio value over time
    st.subheader("💼 Portfolio Balance Over Time")
    if len(df_prices) > 0:
        balance_chart = df_prices[["datetime", "balance"]].copy()
        balance_chart = balance_chart.set_index("datetime")
        st.line_chart(balance_chart, use_container_width=True, height=200)

    # Position sizes over time
    st.subheader("📊 Position Sizes Over Time")
    if len(df_prices) > 0:
        positions_chart = df_prices[["datetime", "up_shares", "down_shares"]].copy()
        positions_chart = positions_chart.set_index("datetime")
        st.line_chart(positions_chart, use_container_width=True, height=200)

    # Real-time price display (from last data point)
    if len(price_points) > 0:
        st.subheader("📡 Current Market State")
        last_point = price_points[-1]
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("UP Price", f"${last_point.up_price:.4f}")
        with col2:
            st.metric("DOWN Price", f"${last_point.down_price:.4f}")
        with col3:
            st.metric("Current Balance", f"${last_point.balance:.2f}")


if __name__ == "__main__":
    main()
