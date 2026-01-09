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


def render_investment_chart(
    price_points: list[PricePoint],
    trade_events: list[TradeEvent],
    initial_balance: float,
) -> None:
    """Render chart showing invested money and value of shares over time.
    
    Args:
        price_points: List of price points over time
        trade_events: List of trade events
        initial_balance: Starting balance
    """
    if not price_points:
        return

    # Create DataFrame with price points
    df = pd.DataFrame(
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

    # Sort trade events by timestamp
    sorted_trades = sorted(trade_events, key=lambda t: t.timestamp)
    
    # Calculate cumulative invested money (total cost): for each timestamp, sum all trades up to that point
    df["invested"] = df["timestamp"].apply(
        lambda ts: sum(t.amount for t in sorted_trades if t.timestamp <= ts)
    )
    
    # Calculate value of shares at each point
    # Value = (up_shares * up_price) + (down_shares * down_price)
    df["shares_value"] = (
        (df["up_shares"] * df["up_price"])
        + (df["down_shares"] * df["down_price"])
    )
    
    # Calculate profit scenarios if each outcome wins
    # If UP wins: UP shares pay $1.00 each, DOWN shares pay $0.00
    # If DOWN wins: UP shares pay $0.00, DOWN shares pay $1.00
    # Profit = payout - total_cost
    df["profit_if_up_wins"] = (df["up_shares"] * 1.0) - df["invested"]
    df["profit_if_down_wins"] = (df["down_shares"] * 1.0) - df["invested"]

    # Create the chart
    fig = go.Figure()

    # Add invested money line
    fig.add_trace(
        go.Scatter(
            x=df["datetime"],
            y=df["invested"],
            mode="lines",
            name="Invested Money",
            line=dict(color="#8B5CF6", width=2),
            hovertemplate="<b>Invested</b><br>"
            + "Time: %{x}<br>"
            + "Amount: $%{y:.2f}<extra></extra>",
        )
    )

    # Add shares value line
    fig.add_trace(
        go.Scatter(
            x=df["datetime"],
            y=df["shares_value"],
            mode="lines",
            name="Value of Shares",
            line=dict(color="#10B981", width=2),
            hovertemplate="<b>Shares Value</b><br>"
            + "Time: %{x}<br>"
            + "Value: $%{y:.2f}<br>"
            + "UP Shares: %{customdata[0]:.2f} @ $%{customdata[2]:.4f}<br>"
            + "DOWN Shares: %{customdata[1]:.2f} @ $%{customdata[3]:.4f}<extra></extra>",
            customdata=[[up, down, up_p, down_p] for up, down, up_p, down_p in 
                       zip(df["up_shares"], df["down_shares"], df["up_price"], df["down_price"])],
        )
    )

    # Add "If UP Wins" profit line
    fig.add_trace(
        go.Scatter(
            x=df["datetime"],
            y=df["profit_if_up_wins"],
            mode="lines",
            name="If UP Wins",
            line=dict(color="#3B82F6", width=2, dash="dot"),
            hovertemplate="<b>If UP Wins</b><br>"
            + "Time: %{x}<br>"
            + "Profit: $%{y:.2f}<br>"
            + "UP Shares: %{customdata[0]:.2f}<br>"
            + "UP Payout: $%{customdata[1]:.2f}<br>"
            + "Total Cost: $%{customdata[2]:.2f}<extra></extra>",
            customdata=[[up, up * 1.0, invested] for up, invested in 
                       zip(df["up_shares"], df["invested"])],
        )
    )

    # Add "If DOWN Wins" profit line
    fig.add_trace(
        go.Scatter(
            x=df["datetime"],
            y=df["profit_if_down_wins"],
            mode="lines",
            name="If DOWN Wins",
            line=dict(color="#EF4444", width=2, dash="dot"),
            hovertemplate="<b>If DOWN Wins</b><br>"
            + "Time: %{x}<br>"
            + "Profit: $%{y:.2f}<br>"
            + "DOWN Shares: %{customdata[0]:.2f}<br>"
            + "DOWN Payout: $%{customdata[1]:.2f}<br>"
            + "Total Cost: $%{customdata[2]:.2f}<extra></extra>",
            customdata=[[down, down * 1.0, invested] for down, invested in 
                       zip(df["down_shares"], df["invested"])],
        )
    )

    # Add initial balance reference line
    fig.add_hline(
        y=initial_balance,
        line_dash="dash",
        line_color="gray",
        annotation_text=f"Initial Balance (${initial_balance:.2f})",
        annotation_position="right",
    )

    # Add zero profit reference line
    fig.add_hline(
        y=0,
        line_dash="dash",
        line_color="gray",
        opacity=0.5,
        annotation_text="Break Even",
        annotation_position="right",
    )

    fig.update_layout(
        title="💰 Investment Performance: Invested Money vs Profit Scenarios",
        xaxis_title="Time",
        yaxis_title="Amount ($)",
        hovermode="x unified",
        height=500,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_white",
    )

    st.plotly_chart(fig, use_container_width=True)


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

