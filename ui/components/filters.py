"""Filter components for the dashboard."""

import streamlit as st


def render_filters() -> dict:
    """Render filter controls and return filter values."""
    st.header("🔍 Filters")
    col1, col2 = st.columns(2)

    with col1:
        profit_filter = st.selectbox(
            "Profit Filter",
            ["All", "Positive Only", "Negative Only"],
            index=0,
        )
        col1a, col1b = st.columns(2)
        with col1a:
            min_profit = st.number_input(
                "Min Profit ($)",
                value=-1000.0,
                step=100.0,
            )
        with col1b:
            max_profit = st.number_input(
                "Max Profit ($)",
                value=1000.0,
                step=100.0,
            )

    with col2:
        st.markdown("**Size Filter (Absolute Profit)**")
        col2a, col2b = st.columns(2)
        with col2a:
            min_size = st.number_input(
                "Min Size ($)",
                value=0.0,
                step=10.0,
                key="min_size",
            )
        with col2b:
            max_size = st.number_input(
                "Max Size ($)",
                value=10000.0,
                step=100.0,
                key="max_size",
            )

    return {
        "profit_filter": profit_filter,
        "min_profit": min_profit,
        "max_profit": max_profit,
        "min_size": min_size,
        "max_size": max_size,
    }

