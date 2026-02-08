# ADR: Separate Risk Limits and Accounting for Paper vs Live

**Status:** Accepted  
**Date:** 2026-02-08  
**Context:** Proposal PROPOSAL_PAPER_LIVE_RISK_LIMITS.md; live execution lane (ADR 2026-02-08-live-execution-lane-routing).

---

## Context

With the live execution lane enabled, Risk ran before lane routing and used a single limits config and a single view of state (approved_trades, order_count). Paper trading (many strategies, immediate simulated fills) consumed the shared risk budget, so live orders were denied by `RISK_MAX_POSITION` and `RISK_RATE_LIMIT` before reaching the live lane. The operator could not validate real order flow because paper activity starved live.

---

## Decision

1. **Lane resolution in Risk**  
   RiskChecker resolves lane (paper vs live) per intent using the same rule as ApprovedProposalRouter: execution enabled and strategy in active set → live; otherwise paper. When execution_control or get_active_strategies is not provided, all intents are treated as paper (backward compatible).

2. **Per-lane state**  
   RiskChecker maintains separate approved_trades, executed_trades, and order_count_last_minute per lane. Context and rate/position checks use only the resolved lane’s state so paper activity does not consume live budget.

3. **Optional per-lane limits**  
   PlatformConfig may define `risk.paper` and `risk.live` in YAML (same shape as current risk block). When both are present, the loader sets risk_paper and risk_live; the orchestrator passes them to RiskChecker as limits_paper and limits_live. Otherwise a single engine.limits is used for both lanes.

4. **Orchestrator wiring**  
   PlatformOrchestrator passes execution_control, get_active_strategies, and (when present) limits_paper and limits_live into RiskChecker.

5. **Observability**  
   RiskCheckEvent has an optional `lane` field. Risk metrics (risk_checks_total, risk_denials_total) include a `lane` label when set.

6. **Rate limit reset**  
   Per-lane order_count counters are reset every N seconds (default 60) so order_rate_limit_per_minute is meaningful. RiskChecker accepts an optional Clock for deterministic tests.

---

## Consequences

- Paper-heavy activity no longer starves live intents; live lane has its own state and optional limits.
- Existing configs without risk.paper/live are unchanged; single risk block applies to both lanes.
- Risk remains the single hard gate (flows.mdc §6); lane resolution and per-lane state are internal to Risk.
- Default safe behavior preserved: when execution_control/get_active_strategies are not provided, all intents use paper state and single limits.

---

## References

- Proposal: `docs/proposals/PROPOSAL_PAPER_LIVE_RISK_LIMITS.md`
- ADR: `docs/adr/2026-02-08-live-execution-lane-routing.md`
- flows.mdc §6 (Pre-Trade Risk)
- observability.mdc (events, metrics)
