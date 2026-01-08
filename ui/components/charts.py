"""Chart components for visualization."""

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui.models import PricePoint, TradeEvent


def render_price_chart(price_points: list[PricePoint], trade_events: list[TradeEvent]) -> None:
    """Render price chart with trade markers."""
    if not price_points:
        return

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

    fig = go.Figure()

    # Add UP price line
    fig.add_trace(
        go.Scatter(
            x=df_prices["datetime"],
            y=df_prices["up_price"],
            mode="lines",
            name="UP Price",
            line=dict(color="#3B82F6", width=2),
        )
    )

    # Add DOWN price line
    fig.add_trace(
        go.Scatter(
            x=df_prices["datetime"],
            y=df_prices["down_price"],
            mode="lines",
            name="DOWN Price",
            line=dict(color="#10B981", width=2),
        )
    )

    # Add trade markers
    if trade_events:
        up_trades = [t for t in trade_events if t.outcome == "UP"]
        down_trades = [t for t in trade_events if t.outcome == "DOWN"]

        if up_trades:
            fig.add_trace(
                go.Scatter(
                    x=[datetime.fromtimestamp(t.timestamp) for t in up_trades],
                    y=[t.price for t in up_trades],
                    mode="markers",
                    name="UP Trades",
                    marker=dict(color="#EF4444", size=10, symbol="triangle-up"),
                    hovertemplate="<b>UP Trade</b><br>"
                    + "Time: %{x}<br>"
                    + "Price: $%{y:.4f}<br>"
                    + "Amount: $%{customdata[0]:.2f}<br>"
                    + "Shares: %{customdata[1]:.4f}<extra></extra>",
                    customdata=[[t.amount, t.shares] for t in up_trades],
                )
            )

        if down_trades:
            fig.add_trace(
                go.Scatter(
                    x=[datetime.fromtimestamp(t.timestamp) for t in down_trades],
                    y=[t.price for t in down_trades],
                    mode="markers",
                    name="DOWN Trades",
                    marker=dict(color="#8B5CF6", size=10, symbol="triangle-down"),
                    hovertemplate="<b>DOWN Trade</b><br>"
                    + "Time: %{x}<br>"
                    + "Price: $%{y:.4f}<br>"
                    + "Amount: $%{customdata[0]:.2f}<br>"
                    + "Shares: %{customdata[1]:.4f}<extra></extra>",
                    customdata=[[t.amount, t.shares] for t in down_trades],
                )
            )

    fig.update_layout(
        title="Market Prices and Trades",
        xaxis_title="Time",
        yaxis_title="Price ($)",
        hovermode="x unified",
        height=500,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_white",
    )

    st.plotly_chart(fig, use_container_width=True)


def render_portfolio_charts(price_points: list[PricePoint]) -> None:
    """Render portfolio balance and position size charts side by side."""
    if not price_points:
        return

    df_prices = pd.DataFrame(
        [
            {
                "timestamp": pp.timestamp,
                "datetime": datetime.fromtimestamp(pp.timestamp),
                "balance": pp.balance,
                "up_shares": pp.up_shares,
                "down_shares": pp.down_shares,
            }
            for pp in price_points
        ]
    )

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("💼 Portfolio Balance Over Time")
        balance_chart = df_prices[["datetime", "balance"]].copy()
        balance_chart = balance_chart.set_index("datetime")
        st.line_chart(balance_chart, use_container_width=True, height=200)

    with col2:
        st.subheader("📊 Position Sizes Over Time")
        positions_chart = df_prices[["datetime", "up_shares", "down_shares"]].copy()
        positions_chart = positions_chart.set_index("datetime")
        st.line_chart(positions_chart, use_container_width=True, height=200)


def render_profit_per_market_chart(df_profits: pd.DataFrame) -> None:
    """Render profit per market bar chart."""
    df_sorted = df_profits.sort_values("Profit", ascending=False)

    fig = go.Figure()
    colors = ["#10B981" if p > 0 else "#EF4444" for p in df_sorted["Profit"]]
    fig.add_trace(
        go.Bar(
            x=df_sorted["Market"],
            y=df_sorted["Profit"],
            marker_color=colors,
            text=df_sorted["Profit"].apply(lambda x: f"${x:+.2f}"),
            textposition="outside",
        )
    )
    fig.update_layout(
        title="Profit by Market",
        xaxis_title="Market",
        yaxis_title="Profit ($)",
        height=400,
        xaxis=dict(tickangle=-45),
        template="plotly_white",
    )
    st.plotly_chart(fig, use_container_width=True)


def render_profit_distribution_charts(df_profits: pd.DataFrame) -> None:
    """Render profit and loss distribution histograms."""
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📈 Profit Distribution")
        profits_only = df_profits[df_profits["Profit"] > 0]["Profit"]
        if len(profits_only) > 0:
            fig = go.Figure()
            fig.add_trace(
                go.Histogram(
                    x=profits_only,
                    nbinsx=20,
                    marker_color="#10B981",
                    name="Profit",
                )
            )
            fig.update_layout(
                title="Distribution of Profits",
                xaxis_title="Profit ($)",
                yaxis_title="Frequency",
                height=300,
                template="plotly_white",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No profitable markets to display")

    with col2:
        st.subheader("📉 Loss Distribution")
        losses_only = df_profits[df_profits["Profit"] < 0]["Profit"]
        if len(losses_only) > 0:
            fig = go.Figure()
            fig.add_trace(
                go.Histogram(
                    x=losses_only,
                    nbinsx=20,
                    marker_color="#EF4444",
                    name="Loss",
                )
            )
            fig.update_layout(
                title="Distribution of Losses",
                xaxis_title="Loss ($)",
                yaxis_title="Frequency",
                height=300,
                template="plotly_white",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No losing markets to display")

