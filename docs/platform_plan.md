# Platform Plan (Proposal Only, No Implementation)
Date: 2026-01-21
Scope: Polymarket platform design with paper-all + multi-live selection

## 1) Objectives
- Run all strategies in paper mode to track performance continuously.
- Allow multiple strategies to be active in live mode at the same time.
- Provide a runtime control plane via API (no authentication for now).
- Maintain strict safety: execution disabled by default and gated by health checks.

## 2) Operating Model (Two Lanes)
Paper lane (always on):
- All strategies run, emit signals, and go through paper OMS/execution.
- Performance tracked per strategy (PnL, drawdown, win rate, etc.).

Live lane (manual selection, multiple active strategies):
- Only strategies marked active in live_strategy_activation are allowed to execute live orders.
- Live execution requires explicit enable command and health gate pass.

Invariant:
intent.strategy_id in live_strategy_activation where active = true

## 3) Execution Control (DB)
execution_control (singleton row):
- execution_enabled: bool
- updated_by: string
- reason: string
- updated_at: timestamp

## 4) Strategy Registry (DB)
strategies:
- strategy_id (PK)
- name
- description
- config (JSONB)
- enabled
- created_at, updated_at

## 5) Live Strategy Activation (DB)
live_strategy_activation:
- strategy_id (FK to strategies)
- active: bool
- activated_at
- activated_by
- reason

## 6) Control Commands (DB Queue)
control_commands:
- command_id (UUID PK)
- command_type: enable_execution | disable_execution | add_active_strategy | remove_active_strategy
- strategy_id (optional)
- reason, issued_by
- status: pending | applied | failed
- created_at, applied_at, error_message

Control plane:
- Polls pending commands and applies to execution_control + live_strategy_activation
- Emits ControlCommandEvent for audit trail

## 7) Control API (No Auth for Now)
Endpoints:
GET  /health
GET  /strategies
POST /strategies
GET  /execution/control
GET  /live/strategies
POST /control/enable
POST /control/disable
POST /control/add-strategy
POST /control/remove-strategy

Note: No authentication at this stage. Consider host/IP restrictions.

## 8) Routing and Enforcement
Strategy identity propagation:
- Signals carry strategy_id (already available as model_id).
- Targets and intents carry strategy_id.

Enforcement:
- Primary: Risk policy denies if strategy_id not active.
- Backstop: ExecutionRouter rejects if strategy_id not active.

## 9) Safety and Health Gating
Enable execution:
- Requires health gates to pass (market data freshness, user stream, reconciliation, kill switch off).
- Issues ExecutionPermitEvent with audit data.

Disable execution:
- Stops new live orders immediately.
- Optional: cancel open live orders (policy decision).

## 10) Discussion Space
1) Should adding/removing active strategies require execution to be disabled first?
2) On remove strategy, do we cancel open live orders or just block new orders?
3) Should active strategies be ordered (priority) or a set only?
4) Should paper mode use the same risk limits as live?
5) Do we want per-strategy risk budgets in Phase 1 or Phase 2?

## 11) Implementation Plan (Logical Commits)
Commit 1: Add strategy_id to intents/targets and propagate from signals.
Commit 2: Add strategies table and repository (registry).
Commit 3: Add execution_control (singleton) and live_strategy_activation table.
Commit 4: Add control_commands queue and repository.
Commit 5: Control plane service consumes DB commands and updates execution_control
          and live_strategy_activation.
Commit 6: Control API endpoints for add/remove/enable/disable and list live set.
Commit 7: Enforce active strategy set in Risk and Execution.
Commit 8: Optional: cancel-on-disable and cancel-on-remove policies.
Commit 9: Docs and runbook for operator actions.
