"""Formatters for task output."""

from datetime import datetime

from polytrader.types import MarketChangeEvent, MarketTick, Order, TradeProposal


class TickFormatter:
    """Formatter for market tick output."""

    @staticmethod
    def format_compact(tick: MarketTick, count: int) -> str:
        """Format tick as compact single line.

        Args:
            tick: Market tick to format
            count: Tick sequence number

        Returns:
            Formatted string
        """
        time_str = datetime.fromtimestamp(tick.ts).strftime("%H:%M:%S")
        market_short = (
            tick.market_slug.split("-")[-1] if "-" in tick.market_slug else tick.market_slug
        )
        spread_abs = abs(tick.spread)
        return (
            f"[{time_str}] #{count:4d}  {market_short:15s}  {tick.outcome:4s}  "
            f"bid:{tick.best_bid:.4f} ask:{tick.best_ask:.4f} "
            f"mid:{tick.mid:.4f} spread:{spread_abs:.4f}"
        )


class ProposalFormatter:
    """Formatter for trade proposal output."""

    @staticmethod
    def format_compact(proposal: TradeProposal) -> str:
        """Format proposal as compact single line.

        Args:
            proposal: Trade proposal to format

        Returns:
            Formatted string
        """
        time_str = datetime.fromtimestamp(proposal.ts).strftime("%H:%M:%S")
        market_short = (
            proposal.market_slug.split("-")[-1]
            if "-" in proposal.market_slug
            else proposal.market_slug
        )
        return (
            f"[{time_str}] 💡 PROPOSAL  {market_short:15s}  {proposal.outcome:4s}  "
            f"{proposal.side:4s}  ${proposal.size:.2f}  @{proposal.limit_price:.4f}  "
            f"target:{proposal.target_price:.4f}  {proposal.reason}"
        )


class OrderFormatter:
    """Formatter for order output."""

    @staticmethod
    def format_compact(order: Order) -> list[str]:
        """Format order as compact lines.

        Args:
            order: Order to format

        Returns:
            List of formatted strings (usually 1-2 lines)
        """
        order_time = datetime.fromtimestamp(order.ts).strftime("%H:%M:%S")
        market_short = (
            order.market_slug.split("-")[-1] if "-" in order.market_slug else order.market_slug
        )

        response = order.response
        if isinstance(response, dict):
            order_id = response.get("order_id") or response.get("id") or "N/A"
            status = response.get("status") or response.get("state") or "N/A"
            fills = response.get("fills", [])

            fill_info = ""
            if fills:
                fill_info = f" ({len(fills)} fill(s))"
            elif status.lower() not in ["filled", "complete"]:
                fill_info = " (pending)"

            error_info = ""
            if "error" in response:
                error_info = f" ⚠️  {response['error']}"

            lines = [
                (
                    f"[{order_time}] ✅ ORDER  {market_short:15s}  {order.outcome:4s}  "
                    f"{order.side:4s}  ${order.size:.2f}  ID:{order_id}  "
                    f"{status}{fill_info}{error_info}"
                )
            ]
            if order.proposal_reason:
                lines.append(f"         Reason: {order.proposal_reason}")
            return lines
        else:
            return [
                (
                    f"[{order_time}] ✅ ORDER  {market_short:15s}  {order.outcome:4s}  "
                    f"{order.side:4s}  ${order.size:.2f}  Response: {response}"
                )
            ]


class MarketChangeFormatter:
    """Formatter for market change events."""

    @staticmethod
    def format_compact(event: MarketChangeEvent) -> str:
        """Format market change event as compact single line.

        Args:
            event: Market change event to format

        Returns:
            Formatted string
        """
        change_time = datetime.fromtimestamp(event.timestamp).strftime("%H:%M:%S")
        if event.old_market:
            old_short = (
                event.old_market.split("-")[-1] if "-" in event.old_market else event.old_market
            )
            new_short = (
                event.new_market.split("-")[-1] if "-" in event.new_market else event.new_market
            )
            return f"[{change_time}] 🔄 Market: {old_short} → {new_short}"
        else:
            new_short = (
                event.new_market.split("-")[-1] if "-" in event.new_market else event.new_market
            )
            return f"[{change_time}] 🚀 Started: {new_short}"
