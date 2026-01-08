"""Table components for displaying data."""

import pandas as pd
import streamlit as st

from ui.models import MarketProfitResult, TradeEvent


def render_trade_events_table(trade_events: list[TradeEvent]) -> None:
    """Render trade events table."""
    if not trade_events:
        return

    from datetime import datetime

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

    st.dataframe(
        df_trades[["datetime", "outcome", "amount", "price", "shares", "balance_after"]].style.format(
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


def render_aggregated_stats_table(
    price_points: list,
    trade_events: list[TradeEvent],
    initial_balance: float,
) -> None:
    """Render aggregated stats table for UP and DOWN outcomes."""
    if not trade_events:
        return

    from datetime import datetime

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

    # Calculate aggregated stats for UP and DOWN
    up_trades = df_trades[df_trades["outcome"] == "UP"]
    down_trades = df_trades[df_trades["outcome"] == "DOWN"]

    # Get final positions from last price point
    final_up_shares = price_points[-1].up_shares if price_points else 0.0
    final_down_shares = price_points[-1].down_shares if price_points else 0.0

    # Calculate total cost per outcome
    up_total_spent = up_trades["amount"].sum() if len(up_trades) > 0 else 0.0
    down_total_spent = down_trades["amount"].sum() if len(down_trades) > 0 else 0.0

    # Calculate average price per outcome (weighted by amount)
    up_avg_price = (
        (up_trades["amount"].sum() / up_trades["shares"].sum())
        if len(up_trades) > 0 and up_trades["shares"].sum() > 0
        else 0.0
    )
    down_avg_price = (
        (down_trades["amount"].sum() / down_trades["shares"].sum())
        if len(down_trades) > 0 and down_trades["shares"].sum() > 0
        else 0.0
    )

    # Calculate total shares per outcome
    up_total_shares = up_trades["shares"].sum() if len(up_trades) > 0 else 0.0
    down_total_shares = down_trades["shares"].sum() if len(down_trades) > 0 else 0.0

    # Calculate profit for each scenario
    profit_if_up_wins = (final_balance + final_up_shares * 1.0) - initial_balance
    profit_if_down_wins = (final_balance + final_down_shares * 1.0) - initial_balance

    profit_if_up_wins_pct = (profit_if_up_wins / initial_balance * 100) if initial_balance > 0 else 0
    profit_if_down_wins_pct = (profit_if_down_wins / initial_balance * 100) if initial_balance > 0 else 0

    # Create aggregated stats table
    aggregated_data = {
        "Metric": [
            "Total Trades",
            "Total Spent",
            "Total Shares",
            "Average Price",
            "Final Shares",
            "Final Profit (if wins)",
            "Final Profit % (if wins)",
        ],
        "UP": [
            len(up_trades),
            f"${up_total_spent:.2f}",
            f"{up_total_shares:.4f}",
            f"${up_avg_price:.4f}" if up_avg_price > 0 else "$0.0000",
            f"{final_up_shares:.4f}",
            f"${profit_if_up_wins:+.2f}",
            f"{profit_if_up_wins_pct:+.2f}%",
        ],
        "DOWN": [
            len(down_trades),
            f"${down_total_spent:.2f}",
            f"{down_total_shares:.4f}",
            f"${down_avg_price:.4f}" if down_avg_price > 0 else "$0.0000",
            f"{final_down_shares:.4f}",
            f"${profit_if_down_wins:+.2f}",
            f"{profit_if_down_wins_pct:+.2f}%",
        ],
    }

    df_aggregated = pd.DataFrame(aggregated_data)
    st.dataframe(df_aggregated, use_container_width=True, hide_index=True)

    # Final profit summary metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Current Balance", f"${final_balance:.2f}")
    with col2:
        st.metric("If UP Wins", f"${profit_if_up_wins:+.2f}")
    with col3:
        st.metric("If DOWN Wins", f"${profit_if_down_wins:+.2f}")


def render_market_details_table(market_profits: list[MarketProfitResult]) -> None:
    """Render market details table."""
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
            for p in market_profits
        ]
    )

    st.dataframe(
        df_profits.sort_values("Profit", ascending=False).style.format(
            {
                "Profit": "${:.2f}",
                "Profit %": "{:.2f}%",
                "Final Balance": "${:.2f}",
                "Total Spent": "${:.2f}",
                "Profit if UP Wins": "${:.2f}",
                "Profit if DOWN Wins": "${:.2f}",
            }
        ),
        use_container_width=True,
        height=400,
    )

