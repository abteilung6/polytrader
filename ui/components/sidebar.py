"""Sidebar component for configuration."""

import streamlit as st

from backtest import find_all_data_files


def render_sidebar() -> dict:
    """Render the sidebar and return configuration."""
    with st.sidebar:
        st.header("⚙️ Configuration")

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

        # Market selection (only show if markets are loaded)
        if "markets" in st.session_state:
            st.markdown("---")
            st.header("📊 Navigation")
            markets = st.session_state.markets
            market_options = list(sorted(markets.keys()))
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

