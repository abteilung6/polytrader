"""Market detail page showing individual market analysis."""

from datetime import datetime

import pandas as pd
import streamlit as st

from cli.commands.backtest import extract_asset_from_market_id
from ui.components.charts import (
    render_investment_chart,
    render_portfolio_charts,
    render_price_chart,
)
from ui.components.tables import render_aggregated_stats_table, render_trade_events_table
from ui.utils import simulate_backtest_with_tracking


def show_market_detail(
    market_id: str,
    csv_files: list[str],
    strategy_name: str,
    initial_balance: float,
) -> None:
    """Show detailed view for a single market."""
    price_points, trade_events = simulate_backtest_with_tracking(
        market_id=market_id,
        csv_files=csv_files,
        strategy_name=strategy_name,
        initial_balance=initial_balance,
    )

    if not price_points:
        st.error("No price data found for this market")
        return

    st.header(f"📈 Market Analysis: {market_id}")
    st.markdown(f"**Asset:** {extract_asset_from_market_id(market_id).upper()}")

    # Price chart with trade markers
    st.subheader("💰 Prices Over Time (with Trade Markers)")
    render_price_chart(price_points, trade_events)

    # Investment performance chart
    if trade_events:
        render_investment_chart(price_points, trade_events, initial_balance)
    
    # Portfolio value and position sizes side by side
    render_portfolio_charts(price_points)

    # Calculate trade data for summary and aggregated stats
    if trade_events:
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
                }
                for te in trade_events
            ]
        )

        final_balance = df_trades["balance_after"].iloc[-1] if len(df_trades) > 0 else initial_balance

        # Trade summary
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Trades", len(trade_events))
        with col2:
            total_spent = df_trades["amount"].sum()
            st.metric("Total Spent", f"${total_spent:.2f}")
        with col3:
            st.metric("Final Balance", f"${final_balance:.2f}")
        with col4:
            # Calculate estimated profit
            final_up_shares = price_points[-1].up_shares if price_points else 0.0
            final_down_shares = price_points[-1].down_shares if price_points else 0.0
            profit_if_up = (final_balance + final_up_shares * 1.0) - initial_balance
            profit_if_down = (final_balance + final_down_shares * 1.0) - initial_balance
            estimated_profit = (profit_if_up + profit_if_down) / 2.0
            profit_pct = (estimated_profit / initial_balance * 100) if initial_balance > 0 else 0
            st.metric("Estimated Profit", f"${estimated_profit:+.2f} ({profit_pct:+.2f}%)")

        # Aggregated stats by outcome and final profit summary
        st.subheader("📊 Aggregated Stats by Outcome & 📈 Final Profit Summary")
        render_aggregated_stats_table(price_points, trade_events, initial_balance)

    # Current market state
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

    # Trade Events table at the bottom
    if trade_events:
        st.subheader("🔔 Trade Events")
        render_trade_events_table(trade_events)

