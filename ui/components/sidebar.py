"""Sidebar component for configuration."""

import re
from datetime import datetime
from pathlib import Path

import streamlit as st

from backtest import find_all_data_files


def extract_date_from_csv_path(csv_path: str) -> str | None:
    """Extract date (YYYY-MM-DD) from CSV file path.
    
    Args:
        csv_path: Path like 'data/market-slug/2025-12-29/.../data.csv'
        
    Returns:
        Date string in YYYY-MM-DD format, or None if not found
    """
    # Try to find YYYY-MM-DD pattern in the path
    date_pattern = r'(\d{4}-\d{2}-\d{2})'
    match = re.search(date_pattern, csv_path)
    if match:
        return match.group(1)
    return None


def get_available_dates(markets: dict[str, list[str]]) -> list[str]:
    """Extract all unique dates from market CSV files.
    
    Args:
        markets: Dictionary mapping market slugs to list of CSV file paths
        
    Returns:
        Sorted list of unique date strings (YYYY-MM-DD)
    """
    dates: set[str] = set()
    for csv_files in markets.values():
        for csv_path in csv_files:
            date = extract_date_from_csv_path(csv_path)
            if date:
                dates.add(date)
    
    return sorted(dates)


def filter_markets_by_date(
    markets: dict[str, list[str]], 
    selected_dates: list[str]
) -> dict[str, list[str]]:
    """Filter markets to only include CSV files from selected dates.
    
    Args:
        markets: Dictionary mapping market slugs to list of CSV file paths
        selected_dates: List of date strings (YYYY-MM-DD) to include
        
    Returns:
        Filtered markets dictionary
    """
    if not selected_dates:
        return markets
    
    filtered: dict[str, list[str]] = {}
    for market_id, csv_files in markets.items():
        filtered_files = [
            csv_path for csv_path in csv_files
            if extract_date_from_csv_path(csv_path) in selected_dates
        ]
        if filtered_files:
            filtered[market_id] = filtered_files
    
    return filtered


def render_sidebar() -> dict:
    """Render the sidebar and return configuration."""
    with st.sidebar:
        st.header("⚙️ Configuration")

        # View selector
        view_mode = st.radio(
            "View Mode",
            ["Main Dashboard", "Navigation Empty", "Filter for Single Market"],
            index=0,
            help="Select the view mode for the main content area"
        )
        st.session_state.view_mode = view_mode

        # Strategy selection
        strategy_name = st.selectbox(
            "Strategy",
            ["gabagool", "gabagool-v2", "gabagool-v3", "gabagool-v4"],
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
        if st.button("🔄 Load Markets", use_container_width=True):
            with st.spinner("Loading markets..."):
                markets = find_all_data_files(data_dir)
                if markets:
                    st.session_state.markets = markets
                    # Clear cached profits when markets are reloaded
                    if "market_profits" in st.session_state:
                        del st.session_state.market_profits
                    st.success(f"✅ Loaded {len(markets)} markets")
                else:
                    st.error(f"❌ No markets found in '{data_dir}'")

        # Day filter and market selection (only show if markets are loaded)
        if "markets" in st.session_state:
            st.markdown("---")
            
            # Day filtering
            st.header("📅 Day Filter")
            markets = st.session_state.markets
            available_dates = get_available_dates(markets)
            
            if available_dates:
                selected_dates = st.multiselect(
                    "Select Days",
                    available_dates,
                    default=available_dates,
                    help="Filter markets by date. Leave empty to show all dates."
                )
                st.session_state.selected_dates = selected_dates
                
                # Filter markets by selected dates
                if selected_dates:
                    filtered_markets = filter_markets_by_date(markets, selected_dates)
                    st.session_state.filtered_markets = filtered_markets
                else:
                    st.session_state.filtered_markets = markets
            else:
                st.info("No dates found in file paths")
                st.session_state.selected_dates = []
                st.session_state.filtered_markets = markets
            
            # Market selection based on view mode
            if view_mode != "Navigation Empty":
                st.markdown("---")
                st.header("📊 Navigation")
                
                # Use filtered markets for market selection
                display_markets = st.session_state.get("filtered_markets", markets)
                market_options = list(sorted(display_markets.keys()))
                
                if view_mode == "Filter for Single Market":
                    # For single market filter mode, require selection
                    if market_options:
                        selected_market = st.selectbox(
                            "Select Market for Detail View",
                            [""] + market_options,
                            help="Select a market to view detailed analysis",
                        )
                        if selected_market:
                            st.session_state.selected_market = selected_market
                        else:
                            st.session_state.selected_market = None
                    else:
                        st.warning("No markets available with selected date filters")
                        st.session_state.selected_market = None
                else:  # Main Dashboard mode
                    selected_market = st.selectbox(
                        "Select Market for Detail View",
                        [""] + market_options,
                        help="Select a market to view detailed analysis, or leave empty for dashboard view",
                    )
                    if selected_market:
                        st.session_state.selected_market = selected_market
                    else:
                        st.session_state.selected_market = None

        return {
            "strategy_name": strategy_name,
            "initial_balance": initial_balance,
        }

