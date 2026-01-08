#!/usr/bin/env python3
"""Main Streamlit app entry point."""

import streamlit as st

from ui.components.filters import render_filters
from ui.components.sidebar import render_sidebar
from ui.pages.dashboard import show_dashboard
from ui.pages.market_detail import show_market_detail


def main():
    """Main Streamlit app."""
    st.set_page_config(
        page_title="Polytrader Backtest Visualizer",
        layout="wide",
        page_icon="📊",
    )

    # Render sidebar and get configuration
    config = render_sidebar()

    # Check if markets are loaded
    if "markets" not in st.session_state:
        st.info("👈 Click 'Load Markets' in the sidebar to get started")
        return

    markets = st.session_state.markets

    # Check if a specific market is selected
    if "selected_market" in st.session_state and st.session_state.selected_market:
        # Show detailed market view
        selected_market = st.session_state.selected_market
        csv_files = markets[selected_market]
        show_market_detail(
            market_id=selected_market,
            csv_files=csv_files,
            strategy_name=config["strategy_name"],
            initial_balance=config["initial_balance"],
        )
    else:
        # Show main dashboard
        filters = render_filters()
        show_dashboard(
            markets=markets,
            strategy_name=config["strategy_name"],
            initial_balance=config["initial_balance"],
            filters=filters,
        )


if __name__ == "__main__":
    main()
