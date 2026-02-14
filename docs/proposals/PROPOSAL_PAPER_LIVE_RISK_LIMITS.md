# Proposal: Separate Risk Limits and Accounting for Paper vs Live

**Status:** Accepted (implemented 2026-02-08)  
**Date:** 2026-02-08  
**Related:** PROPOSAL_LIVE_EXECUTION_LANE.md, ADR 2026-02-08-live-execution-lane-routing, platform.live-pilot.yaml

**Authoritative rules (must comply):** `.cursor/rules/` — flows.mdc, architecture.mdc, rules.mdc, trading.mdc, testing.mdc, unit_testing_techinical.mdc, observability.mdc.

---

## 0. Compliance with Project Rules

This proposal and its implementation must conform to the following. Refs: **flows.mdc**, **architecture.mdc**, **rules.mdc**, **testing.mdc**, **unit_testing_techinical.mdc**, **observability.mdc**.

**Flow compliance (rules.mdc § Flow Compliance Check):**

1. **Which section of flows.mdc does this change belong to?**  
   §6 (Pre-Trade Risk). Risk remains the single hard gate; we only change how context and limits are selected (per-lane state and optional per-lane limits). No stage skipped or reordered.

2. **Upstream/downstream:**  
   Upstream: PROPOSALS (unchanged). Downstream: APPROVED_PROPOSALS (unchanged). ApprovedProposalRouter and OMS/Execution unchanged. RiskChecker internal state and config loading change only.

3. **Events emitted:**  
   RiskCheckEvent gains optional `lane` field. No new event types. Risk continues to emit RiskCheckEvent always; approved intents still published to APPROVED_PROPOSALS.

4. **Replay/restart:**  
   Lane is deterministic from execution_control and active_strategies. Same intent + same runtime state → same lane and same allow/deny. Restart: per-lane state is in-memory and resets; limits from config.

**Architecture (architecture.mdc):**  
- Risk remains a hard gate; no business logic in adapters.  
- Data contracts: RiskContext and RiskLimits only; no raw dicts across boundaries.  
- Config: validated, versioned (limits_version in context).

**Testing (testing.mdc, unit_testing_techinical.mdc):**  
- Unit tests: deterministic, no DB/network/clocks/sleeps; naming `test_<behavior>_<condition>_<expected_outcome>`; file layout mirrors source (e.g. `tests/unit/risk/`).  
- Assert on **events** and **domain outcomes** (allowed/denied, reason codes, lane), not internal call order.  
- Risk correctness: hard veto and reason codes per lane must be covered.  
- CI: `make lint && make type-check && make test` (and integration where applicable).

**Atomic correctness (rules.mdc §12):**  
- Each commit leaves the system buildable and tests passing. No partial migrations.

---

## 1. Problem Summary

**Symptom:** With the live execution lane enabled and execution enabled, paper trading fills very quickly (many strategies × immediate simulated fills). Shared risk limits (position and rate) are consumed by paper activity, so **live orders are denied** by `RISK_MAX_POSITION` and `RISK_RATE_LIMIT` before they can reach the live lane. The operator cannot validate real order flow because paper “starves” live.

**Root cause:** Risk uses a **single** limits config and a **single** view of state:

- One `RiskLimits` instance (one `max_position_per_market`, one `order_rate_limit_per_minute`, etc.).
- One `RiskContext` per check: positions and order count are **aggregated across all activity** (paper + live). Risk does not know whether the current intent will be routed to paper or live when building context; it applies the same limits to every proposal.
- Position context is derived from `_executed_trades` and `_approved_trades` (and optionally ORDERS); both paper and live approvals/fills contribute to the same sets and counters.

So paper fills and approvals consume the same “budget” as live, and with 20 strategies and fast paper fills, the budget is exhausted before any live proposal can pass.

---

## 2. Current State (Code Deep-Dive)

### 2.1 Risk limits and context

| Component | Location | Behavior |
|-----------|----------|----------|
| **RiskLimits** | `polytrader/risk/models.py` | Single model: `max_position_per_market`, `max_position_global`, `order_rate_limit_per_minute`, etc. No `paper` vs `live` nesting. |
| **RiskContext** | `polytrader/risk/models.py` | Has `current_positions`, `global_position`, `order_count_last_minute`, `executed_trades`, `active_strategies`, `is_paper_mode`. Latter two are **not** set in `RiskChecker._build_context()` — they default to `set()` and `True`. |
| **Config** | `config/platform.live-pilot.yaml` | Single `risk:` block; one set of limits for the whole platform. |

### 2.2 Where context is built

- **RiskChecker** (`polytrader/risk/engine.py`):
  - Subscribes to **PROPOSALS** (all intents) and **ORDERS** (for executed trades).
  - `_build_context(intent)` builds positions from `_executed_trades` and `_approved_trades` (no separation by execution mode). Uses `_order_count_last_minute` (single counter) for rate limit.
  - Does **not** receive `position_manager`; does **not** set `active_strategies` or `is_paper_mode` in the returned context.
  - Publishes approved intents to **APPROVED_PROPOSALS** (single topic). **ApprovedProposalRouter** then routes to APPROVED_PROPOSALS_PAPER or APPROVED_PROPOSALS_LIVE.

So risk runs **before** lane routing. It has no notion of “this intent will go to paper” vs “this intent will go to live” when building context or applying limits.

### 2.3 Order and position flow

- **Paper lane:** OMS subscribes to APPROVED_PROPOSALS_PAPER → execution router → PaperExecutionAdapter → immediate fill → OMS publishes **FILLS** (and ORDER_ACKS). No `OrderExecutedEvent` publish to **ORDERS** in production code (only in tests).
- **Live lane:** OMS subscribes to APPROVED_PROPOSALS_LIVE → live execution router → ClobVenueAdapter → FILLS/ORDER_ACKS when venue responds.
- **Risk** increments `_order_count_last_minute` on **every** approval (line 257); it does not distinguish paper vs live. Position context is built from `_executed_trades` (from ORDERS) and `_approved_trades` (from approvals). So all approvals and (if ORDERS were populated) all fills contribute to one shared position and one shared rate count.

### 2.4 Policies that use shared state

- **check_position_limits:** Uses `context.current_positions` and `context.global_position` (single view).
- **check_rate_limits:** Uses `context.order_count_last_minute` (single counter).
- **check_max_trades_per_market:** Uses `context.executed_trades` (single set).
- **check_strategy_activation:** Uses `context.is_paper_mode` and `context.active_strategies` (currently not wired in orchestrator → risk, so defaults apply).

Conclusion: To allow live orders to pass while paper is active, we must either **split limits by execution mode** and/or **split position/rate accounting by execution mode**.

---

## 3. Institutional Best Practices (Elite Trading Firms)

Practices at Citadel, Jane Street, Jump, and similar firms relevant here:

1. **Separate books for simulated vs real**
   - Sim (paper) and prod (live) maintain separate position and PnL books. Risk limits are applied **per book** so that sim activity cannot consume prod capacity.
2. **Rate limits are per-environment**
   - Live order/cancel rate limits are set for real capital and venue constraints; paper often has its own (higher or separate) limits so that stress testing and strategy count do not block live.
3. **Position limits are capital/risk-based for live only**
   - Live limits reflect real capital and risk appetite. Paper limits can be higher or unbounded for research; they must not share a single global cap with live.
4. **Pre-trade risk sees “which book”**
   - The risk engine knows whether the order is destined for sim or prod (e.g. via routing tag or order type) and selects the appropriate limits and state (positions, rate counters) for that book.

So the industry pattern is: **separate risk state and limits per execution mode (paper vs live)**, with risk decisions using the correct bucket for the intent’s destination lane.

---

## 4. Design Options

### Option A: Split limits only (config)

- **Config:** e.g. `risk.paper` and `risk.live` with separate `RiskLimits`-shaped blocks.
- **Context:** Risk still builds one `current_positions` and one `order_count_last_minute`. When evaluating an intent, we would need to know “will this go to paper or live?” **before** risk runs — but today routing happens **after** risk (risk → APPROVED_PROPOSALS → router → paper/live). So we’d have to either (i) move routing before risk (so risk gets “lane” per intent), or (ii) run risk twice (once with paper limits, once with live limits) and then route — both of which are invasive.
- **Verdict:** Not sufficient alone; we also need per-lane **state** (positions and rate count) so that paper activity doesn’t consume live limits.

### Option B: Split accounting only (state per lane)

- **State:** Maintain separate position and rate counters for “paper” and “live” (e.g. `_executed_trades_paper`, `_executed_trades_live`, `_order_count_paper`, `_order_count_live`). When building context for a given intent, we must know its **destination lane** so we can use the right state.
- **Problem:** Risk runs on PROPOSALS before routing. So at check time we don’t yet know the lane unless we **pre-compute** it (using same logic as ApprovedProposalRouter: `execution_enabled` and `strategy_id in active_strategies`). That is feasible: risk can take `execution_control` and `get_active_strategies` and compute “would this go to live?” and then choose the appropriate state bucket and limits.
- **Limits:** Can remain single for now, or we can add split limits (Option A) so paper can have higher caps.

### Option C: Split limits + split accounting (recommended)

- **Config:** Add optional `risk.paper` and `risk.live` (each with same shape as current `risk`). If absent, fall back to single `risk` for both (backward compatible).
- **RiskChecker:** Receives `execution_control` and `get_active_strategies`. For each intent, **computes destination lane** (live iff execution_enabled and strategy_id in active_strategies; else paper). Builds context using **lane-specific** position and rate state; applies **lane-specific** limits (or shared limits if not split).
- **State:** Separate `_executed_trades_paper`, `_executed_trades_live`, `_approved_trades_paper`, `_approved_trades_live`, and separate rate counters per lane. Optionally tag events (e.g. FillEvent / OrderExecutedEvent) with `execution_mode` so risk can attribute orders to the correct lane when consuming ORDERS (if we add a unified ORDERS feed with mode tag).
- **Result:** Paper activity consumes only paper limits and paper state; live activity consumes only live limits and live state. Live orders can pass even when paper is busy.

This aligns with institutional practice: separate books (state) and separate limits per execution mode.

---

## 5. Recommended Implementation Plan

### 5.1 Principles

- **Backward compatibility:** If config does not specify `risk.paper` / `risk.live`, use a single `risk` block for both lanes (current behavior).
- **Single risk gate:** Risk still runs once per proposal; no duplicate checks. Lane is derived deterministically from execution_control + active_strategies.
- **Observability:** Emit risk checks with a field indicating which lane (paper/live) and which limits bucket were used; log and metrics for denials by lane.

### 5.2 Config schema (additive)

```yaml
# Existing (unchanged): single risk block still supported
risk:
  max_position_per_market: 1.0
  order_rate_limit_per_minute: 10
  # ...

# New (optional): split limits
risk:
  # Optional: when present, paper and live use these instead of top-level risk
  paper:
    max_position_per_market: 10.0
    max_position_global: 50.0
    order_rate_limit_per_minute: 120
    # ... same shape as RiskLimits
  live:
    max_position_per_market: 1.0
    max_position_global: 5.0
    order_rate_limit_per_minute: 10
    # ...
  # If both paper and live are present, they are used per lane.
  # If only one is present, treat as error or fall back to top-level (TBD).
```

Platform config loader: map to two `RiskLimits` instances (`limits_paper`, `limits_live`) or one shared when not split.

### 5.3 RiskChecker and context building

- **RiskChecker constructor:** Add optional `execution_control: ExecutionControl | None`, `get_active_strategies: Callable[[], set[str]] | None`, and `limits_paper: RiskLimits | None`, `limits_live: RiskLimits | None`. When `limits_paper`/`limits_live` are None, use single `engine.limits` for both (current behavior).
- **Lane for an intent:**  
  `is_live = (execution_control is not None and execution_control.is_enabled() and get_active_strategies is not None and intent.strategy_id in get_active_strategies())`.  
  Else paper.
- **State:**  
  - `_executed_trades_paper`, `_executed_trades_live` (or keep one set and tag events with mode when publishing — see below).  
  - `_approved_trades_paper`, `_approved_trades_live`.  
  - `_order_count_last_minute_paper`, `_order_count_last_minute_live` (with optional per-minute decay or sliding window in a later phase; for MVP a simple counter per lane is enough if we reset or decay elsewhere).
- **When an intent is approved:** Increment the **lane’s** rate counter and add to **lane’s** approved_trades (for max_trades and position projection). We know the lane because we computed it before calling `engine.check(context)`.
- **When building context for an intent:** Use the intent’s lane to select:
  - `current_positions` / `global_position` from that lane’s executed + approved state.
  - `order_count_last_minute` from that lane’s counter.
  - `limits` from that lane’s RiskLimits (or shared limits if not split).
- **ORDERS subscription:** Today nothing in production publishes to ORDERS. For a clean design, either (i) have execution routers (paper and live) publish an order-executed event to a **single** topic with an `execution_mode` field so risk can attribute to the correct lane, or (ii) keep building position from approved_trades only for the lane (approved → then filled on that lane, so we can count approvals per lane and treat “filled” as eventual). Option (ii) is simpler short-term: we only need to maintain approved/executed per lane and ensure that when we get an order event (if we add it), we tag it by lane. So: **Phase 1** use only approved_trades + executed_trades per lane; risk does not need ORDERS if we maintain lane-specific approved sets and increment executed when we have a lane-tagged fill (or when we add ORDERS with mode, subscribe and split). For MVP we can derive “executed” per lane from approved_trades that have been “realized” by a fill on that lane — but that requires the risk checker to learn about fills per lane. Simpler MVP: **only split rate limit and position by lane using approved_trades + optional executed_trades**. Position for a lane = sum of approved (and optionally executed) for that lane. So we need execution routers or a central place to publish “order filled on lane X” so risk can move from approved to executed for that lane. Alternatively, keep a single ORDERS topic and add `execution_mode` to the event so risk can attribute to paper vs live. That requires ExecutionRouter (paper and live) to publish to ORDERS with execution_mode. So:
  - **Recommendation:** Add `execution_mode: Literal["paper", "live"]` to the event that risk uses for “executed” (either OrderExecutedEvent on ORDERS or a new event). Paper and live execution paths publish that event with the correct mode. RiskChecker subscribes and updates `_executed_trades_paper` or `_executed_trades_live`. If we don’t want to add ORDERS publish in production yet, we can rely only on _approved_trades per lane for position projection and treat “approved” as “will fill” for that lane (optimistic). That can over-count if orders are rejected after approval; for pilot we can accept that and add executed-tracking in a follow-up.

Simplest MVP: **Split only rate limit and “position” (approved + executed) by lane.**  
- Rate: two counters, increment the lane’s counter on approval.  
- Position: two sets of (strategy_id, market_slug, outcome) for approved; two for executed. When we build context for an intent, we use the lane’s approved+executed to compute current_positions and global_position for that lane. We don’t need ORDERS in production for MVP if we treat “approved on lane” as the position delta (and optionally later add ORDERS with execution_mode to move to executed). So: **no ORDERS change in MVP**; risk only uses _approved_trades and _executed_trades per lane. Executed per lane: we don’t have a source yet unless we add one. So for MVP we can use only _approved_trades per lane for position (assume every approved becomes a fill on that lane). That gives us per-lane position projection and per-lane rate limit. We can add executed-from-ORDERS in a follow-up.

### 5.4 Wiring from platform

- **PlatformOrchestrator** (or platform_start_task): When creating RiskChecker, pass `execution_control`, `get_active_strategies`, and if config has split risk, pass `limits_paper` and `limits_live`. RiskChecker uses them as above.
- **Config:** PlatformConfig gains optional `risk_paper: RiskLimits | None`, `risk_live: RiskLimits | None` (or a small struct). Load from `config["risk"]["paper"]` and `config["risk"]["live"]` when present.

### 5.5 Events and metrics

- **RiskCheckEvent:** Add optional `lane: "paper" | "live"` and `limits_version` (or which limits block) so logs and downstream can see which bucket was used.
- **Metrics:** e.g. `risk_checks_total{lane="paper", allowed="true/false"}`, `risk_denials_total{lane="live", reason="RISK_RATE_LIMIT"}` so operators can see paper vs live denials.

### 5.6 Phasing (context only; detailed tests and acceptance criteria are in §7 Logical Commits)

- **Phase 1 (MVP):** Per-lane state (approved_trades, order_count), per-lane limits when configured, rate reset per lane. Unblocks live orders when paper is busy.
- **Phase 2 (optional):** ORDERS with execution_mode; risk maintains _executed_trades per lane.
- **Phase 3 (optional):** Sliding-window rate limit per lane.


---

## 6. Summary

| Item | Recommendation |
|------|-----------------|
| **Problem** | Paper fills consume shared risk limits; live orders are denied. |
| **Approach** | Separate risk **state** (positions, rate count) and **limits** per execution mode (paper vs live). |
| **Lane at risk time** | Compute from execution_control.is_enabled() and strategy_id in active_strategies (same as ApprovedProposalRouter). |
| **Config** | Optional `risk.paper` and `risk.live`; fallback to single `risk` for backward compatibility. |
| **MVP** | Per-lane approved_trades and order_count; per-lane limits when configured; rate reset per lane. |
| **Follow-up** | ORDERS with execution_mode for executed-trade attribution; sliding-window rate limit. |

---

## 7. Logical Commits (Implementation Plan)

Commits are ordered so each step is testable and align with flows.mdc, architecture.mdc, rules.mdc, testing.mdc, unit_testing_techinical.mdc. Each commit must leave the system buildable with passing tests (atomic correctness).

---

### Commit 1: Lane resolution helper and RiskChecker constructor (risk layer only)

**Goal:** Introduce lane concept and optional per-lane limits at the risk boundary. No behavior change when new args are not provided.

**Changes:**

- **polytrader/risk/engine.py**
  - Add a pure helper (e.g. `_resolve_lane(intent, execution_control, get_active_strategies) -> Literal["paper", "live"]`): returns `"live"` iff `execution_control is not None and execution_control.is_enabled() and get_active_strategies is not None and intent.strategy_id in get_active_strategies()`; else `"paper"`. When any of the three is None, treat as paper.
  - **RiskChecker.__init__:** Add optional `execution_control: ExecutionControl | None = None`, `get_active_strategies: Callable[[], set[str]] | None = None`, `limits_paper: RiskLimits | None = None`, `limits_live: RiskLimits | None = None`. Store them. Do not change `_build_context` or `run()` yet.
- Ensure `ExecutionControl` is importable from a place risk can use (e.g. polytrader.ops.control).

**Tests (unit_testing_techinical.mdc: deterministic, no I/O, naming):**

- **tests/unit/risk/test_lane_resolution.py** (new)
  - `test_resolve_lane_returns_paper_when_execution_control_none`
  - `test_resolve_lane_returns_paper_when_execution_disabled`
  - `test_resolve_lane_returns_paper_when_get_active_strategies_none`
  - `test_resolve_lane_returns_paper_when_strategy_not_in_active_set`
  - `test_resolve_lane_returns_live_when_enabled_and_strategy_active`
- Use mock `ExecutionControl` and a callable returning a fixed set. No network, no DB, no real clock.

**Acceptance criteria:**

- Lane helper returns `"paper"` or `"live"` as specified for all combinations of None/enabled/disabled and strategy in/out of set.
- RiskChecker accepts new optional args and existing call sites still work without passing them (backward compatible).

**Gate:** `make lint && make type-check && make test`.

---

### Commit 2: Per-lane state in RiskChecker (approved_trades and order_count)

**Goal:** Maintain separate approved_trades and order_count per lane; build RiskContext from the lane corresponding to the intent so position and rate checks use lane-specific state.

**Changes:**

- **polytrader/risk/engine.py**
  - Replace `_approved_trades` with `_approved_trades_paper` and `_approved_trades_live`. Replace `_order_count_last_minute` with `_order_count_last_minute_paper` and `_order_count_last_minute_live`. Replace `_approved_correlation` with lane-aware tracking so on approval we add to the lane's set.
  - In `run()`: for each proposal, compute lane via `_resolve_lane`. In `_build_context(intent)`: compute lane; build `current_positions` and `global_position` from the **lane's** approved (and executed) sets only; set `order_count_last_minute` from the **lane's** counter. Select limits: if `limits_paper`/`limits_live` are set, use the lane's limits; else use `engine.limits` for both.
  - On approval: increment the lane's counter and add to the lane's approved_trades. For MVP, ORDERS subscription can remain and attribute to paper when not tagged, or defer to Phase 2.
  - **Backward compat:** When `execution_control` and `get_active_strategies` are both None, lane is always paper; only paper state is ever used.

**Tests:**

- **tests/unit/risk/test_checker_lane_state.py** (new). Component: RiskChecker. Stage: Risk (flows.mdc §6). Contract: context and limits are lane-specific.
  - `test_approval_increments_paper_counter_when_lane_paper`
  - `test_approval_increments_live_counter_when_lane_live`
  - `test_build_context_uses_paper_state_for_paper_lane_intent`
  - `test_build_context_uses_live_state_for_live_lane_intent`
  - `test_paper_approvals_do_not_affect_live_rate_limit`
- Use mock bus, mock ExecutionControl, fixed get_active_strategies; assert on context fields and which lane's counter incremented. No DB/network.

**Acceptance criteria:**

- Two intents (one paper, one live): paper approval only updates paper state; live only live state. Context for a live intent shows live state and does not include paper-approved trades in position.
- When execution_control/get_active_strategies are None, all intents use paper state and single engine.limits (unchanged behavior).

**Gate:** `make lint && make type-check && make test`.

---

### Commit 3: PlatformConfig and loader for optional risk.paper / risk.live

**Goal:** Load optional `risk.paper` and `risk.live` from platform YAML; produce two RiskLimits when both present; otherwise use single risk block for both (backward compatible).

**Changes:**

- **Config schema:** Support `risk: { paper?: { ... }, live?: { ... } }` where each nested block has the same shape as current `risk` (RiskLimits fields). If both `paper` and `live` are present, parse to two `RiskLimits`; if only one, fall back to single risk or require both (document).
- **Platform config loader:** Add `risk_paper: RiskLimits | None = None`, `risk_live: RiskLimits | None = None`. When `config["risk"]` has `"paper"` and `"live"`, load each and set both; else leave None.

**Tests:**

- **tests/unit/platform/test_config_risk_limits.py** or under existing config tests
  - `test_load_risk_config_without_paper_live_returns_single_limits`
  - `test_load_risk_config_with_paper_and_live_returns_two_limits`
- Deterministic; no I/O except in-memory config dict.

**Acceptance criteria:**

- Existing configs without `risk.paper`/`risk.live` load unchanged. Config with both yields two distinct RiskLimits.

**Gate:** `make lint && make type-check && make test`.

---

### Commit 4: Orchestrator wires execution_control, get_active_strategies, and optional limits into RiskChecker

**Goal:** Platform passes execution_control and get_active_strategies into RiskChecker; when config has split risk, pass limits_paper and limits_live.

**Changes:**

- **polytrader/platform/orchestrator.py:** When constructing RiskChecker, pass `execution_control=self._execution_control`, `get_active_strategies=self._get_active_strategies`, and if platform_config has `risk_paper`/`risk_live`, pass `limits_paper` and `limits_live`; else None.
- **polytrader/tasks/platform.py:** Ensure loaded PlatformConfig includes risk_paper/risk_live from Commit 3.

**Tests:**

- **tests/integration/test_risk_paper_live_lanes.py** (new)
  - Start platform (or minimal orchestrator + risk checker) with execution disabled; feed proposals; assert paper state used. Enable execution and add one strategy to active_strategies; feed one proposal for that strategy; assert allowed and live state used. Assert paper-heavy activity does not deny a subsequent live intent when live limits allow.
- Optional unit: orchestrator builds RiskChecker with new args when provided.

**Acceptance criteria:**

- With execution disabled, risk uses paper lane for all. With execution enabled and strategy in active set, that strategy's intents use live lane and live limits when configured. Many paper approvals do not starve one live intent.

**Gate:** `make lint && make type-check && make test` (including integration).

---

### Commit 5: RiskCheckEvent and metrics include lane

**Goal:** Observability: risk checks and denials attributable to paper vs live lane.

**Changes:**

- **polytrader/events/types.py:** Add optional `lane: Literal["paper", "live"] | None = None` to RiskCheckEvent.
- **polytrader/risk/engine.py:** When emitting RiskCheckEvent, set `lane` to the resolved lane.
- **polytrader/obs/metrics.py:** Include `lane` in risk metrics (e.g. `record_risk_check(..., lane=...)`, `record_risk_denial(..., lane=...)`).

**Tests:**

- **tests/unit/risk/test_risk_check_event_lane.py** or extend existing
  - `test_risk_check_event_contains_paper_lane_when_intent_paper`
  - `test_risk_check_event_contains_live_lane_when_intent_live`
- Assert on emitted event (events as audit truth, testing.mdc §6).

**Acceptance criteria:**

- Every RiskCheckEvent has `lane` set. Metrics record lane where applicable.

**Gate:** `make lint && make type-check && make test`.

---

### Commit 6: Rate limit counter reset per lane (periodic)

**Goal:** Make order_rate_limit_per_minute meaningful by resetting per-lane counters periodically (e.g. every 60s).

**Changes:**

- **polytrader/risk/engine.py:** In RiskChecker, every N seconds (e.g. 60) set both lane counters to 0. Use injected Clock for determinism in tests (unit_testing_techinical.mdc: no real time).

**Tests:**

- **tests/unit/risk/test_checker_rate_reset.py**
  - Use FixedClock or similar; trigger reset; assert counters zero after reset and that approval within limit is allowed.
  - `test_rate_counter_reset_clears_both_lanes`
  - `test_after_reset_approval_within_limit_allowed`

**Acceptance criteria:**

- After reset, both lane counters are 0. Rate limit allows new approvals up to limit per lane.

**Gate:** `make lint && make type-check && make test`.

---

### Commit 7: Documentation and ADR update

**Goal:** Document the change and record the decision.

**Changes:**

- **docs/adr/YYYY-MM-DD-paper-live-risk-limits.md:** Context, Decision, Consequences, Status.
- **docs/proposals/PROPOSAL_PAPER_LIVE_RISK_LIMITS.md:** Update status when merged.
- **config/platform.live-pilot.yaml** (optional): Add commented example for `risk.paper` and `risk.live`.

**Tests:** None (docs only).

**Acceptance criteria:** ADR present; proposal status updated; config example clear.

**Gate:** `make lint && make type-check && make test`.

---

## 8. CI and Gates (Summary)

- Every commit: `make format && make lint && make type-check && make test`.
- Integration tests run for Commit 4 and any later commit touching platform startup.
- Risk-critical commits (1, 2, 4, 5, 6) have unit tests with explicit component/stage/contract alignment per unit_testing_techinical.mdc §1.
