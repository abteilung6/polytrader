"""Integration tests for the trading system.

Integration tests verify interactions between multiple components,
end-to-end flows, and system-level behavior.

Per testing.md:
- Integration tests use fake venue adapters (deterministic)
- Replay canned market/user-stream sequences
- Assert emitted events + resulting projections (orders/positions)
"""
