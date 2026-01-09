"""Dashboard page showing aggregated market statistics."""

import pandas as pd
import streamlit as st

from ui.components.charts import render_profit_distribution_charts, render_profit_per_market_chart
from ui.components.tables import render_market_details_table
from ui.models import MarketProfitResult
from ui.utils import calculate_market_profit


def show_dashboard(
    markets: dict[str, list[str]],
    strategy_name: str,
    initial_balance: float,
    filters: dict,
) -> None:
    """Show main dashboard with aggregated statistics."""
    st.header("📊 Market Performance Dashboard")

    # Create a cache key based on markets, strategy, and initial balance
    markets_key = tuple(sorted(markets.keys()))
    markets_hash = hash(markets_key)
    cache_key = f"market_profits_{markets_hash}_{strategy_name}_{initial_balance}"
    
    # Check if we need to recalculate (markets changed or cache missing)
    current_markets_hash = st.session_state.get("current_markets_hash")
    if cache_key not in st.session_state or current_markets_hash != markets_hash:
        with st.spinner("Calculating profits for all markets..."):
            market_profits = []
            progress_bar = st.progress(0)
            total_markets = len(markets)

            for idx, (market_id, csv_files) in enumerate(markets.items()):
                try:
                    result = calculate_market_profit(
                        market_id=market_id,
                        csv_files=csv_files,
                        strategy_name=strategy_name,
                        initial_balance=initial_balance,
                    )
                    market_profits.append(result)
                except Exception as e:
                    st.warning(f"Error calculating profit for {market_id}: {e}")

                progress_bar.progress((idx + 1) / total_markets)

            st.session_state[cache_key] = market_profits
            st.session_state.current_markets_hash = markets_hash
            progress_bar.empty()

    market_profits: list[MarketProfitResult] = st.session_state.get(cache_key, [])

    # Apply filters
    filtered_profits = market_profits.copy()

    if filters["profit_filter"] == "Positive Only":
        filtered_profits = [p for p in filtered_profits if p.profit > 0]
    elif filters["profit_filter"] == "Negative Only":
        filtered_profits = [p for p in filtered_profits if p.profit < 0]

    # Filter by profit value
    filtered_profits = [
        p for p in filtered_profits if filters["min_profit"] <= p.profit <= filters["max_profit"]
    ]

    # Filter by size (absolute value)
    filtered_profits = [
        p
        for p in filtered_profits
        if filters["min_size"] <= abs(p.profit) <= filters["max_size"]
    ]

    if not filtered_profits:
        st.info("No markets match the current filters.")
        return

    # Create DataFrame for easier manipulation
    df_profits = pd.DataFrame(
        [
            {
                "Market": p.market_id,
                "Profit": p.profit,
                "Profit %": p.profit_pct,
                "Final Balance": p.final_balance,
                "Total Trades": p.total_trades,
                "Total Spent": p.total_spent,
                "Profit if UP Wins": p.profit_if_up_wins,
                "Profit if DOWN Wins": p.profit_if_down_wins,
            }
            for p in filtered_profits
        ]
    )

    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Markets", len(filtered_profits))
    with col2:
        total_profit = df_profits["Profit"].sum()
        st.metric("Total Profit", f"${total_profit:+.2f}")
    with col3:
        avg_profit = df_profits["Profit"].mean()
        st.metric("Average Profit", f"${avg_profit:+.2f}")
    with col4:
        profitable_markets = len(df_profits[df_profits["Profit"] > 0])
        st.metric("Profitable Markets", f"{profitable_markets}/{len(filtered_profits)}")

    # Profit per market chart
    st.subheader("💰 Profit per Market")
    render_profit_per_market_chart(df_profits)

    # Profit and Loss distributions
    st.subheader("📊 Profit & Loss Distributions")
    render_profit_distribution_charts(df_profits)

    # Market table
    st.subheader("📋 Market Details")
    render_market_details_table(filtered_profits)

