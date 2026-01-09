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

    # Get view mode
    view_mode = st.session_state.get("view_mode", "Main Dashboard")

    # Check if markets are loaded
    if "markets" not in st.session_state:
        st.info("👈 Click 'Load Markets' in the sidebar to get started")
        return

    # Get filtered markets based on date selection
    markets = st.session_state.get("filtered_markets", st.session_state.markets)

    # Handle different view modes
    if view_mode == "Navigation Empty":
        # Show empty navigation state
        st.header("📊 Navigation Empty")
        st.info("Navigation is currently empty. Select a different view mode to see content.")
        return
    
    elif view_mode == "Filter for Single Market":
        # Only show market detail if a market is selected
        if "selected_market" in st.session_state and st.session_state.selected_market:
            selected_market = st.session_state.selected_market
            if selected_market in markets:
                csv_files = markets[selected_market]
                show_market_detail(
                    market_id=selected_market,
                    csv_files=csv_files,
                    strategy_name=config["strategy_name"],
                    initial_balance=config["initial_balance"],
                )
            else:
                st.error(f"Selected market '{selected_market}' not found in filtered markets.")
                st.info("Please select a market from the sidebar.")
        else:
            st.info("👈 Please select a market from the sidebar to view its details.")
            if not markets:
                st.warning("No markets available with the current date filters. Please adjust your date selection.")
    
    else:  # Main Dashboard mode
        # Check if a specific market is selected
        if "selected_market" in st.session_state and st.session_state.selected_market:
            # Show detailed market view
            selected_market = st.session_state.selected_market
            if selected_market in markets:
                csv_files = markets[selected_market]
                show_market_detail(
                    market_id=selected_market,
                    csv_files=csv_files,
                    strategy_name=config["strategy_name"],
                    initial_balance=config["initial_balance"],
                )
            else:
                st.warning(f"Selected market '{selected_market}' not found. Showing dashboard instead.")
                filters = render_filters()
                show_dashboard(
                    markets=markets,
                    strategy_name=config["strategy_name"],
                    initial_balance=config["initial_balance"],
                    filters=filters,
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
