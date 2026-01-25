# Architecture Overview — Polytrader

This document provides a high-level overview of the Polytrader system architecture, component responsibilities, and the distinction between live and paper trading modes.

**Authoritative References:**
- `.cursor/rules/architecture.mdc` — Detailed module boundaries and responsibilities
- `.cursor/rules/flows.mdc` — Canonical trading pipeline flows
- `.cursor/rules/vision.mdc` — Repository structure and ownership model

---

## System Overview

Polytrader is an institutional-grade trading system for Polymarket that follows a deterministic, event-sourced architecture with strict separation of concerns.

### Core Pipeline

```
Market Data → State Builders → Strategy → Portfolio → Risk → OMS → Execution → Venue
     ↓                                                                          ↓
Event Store ←──────────────────────────────────────────────────────────────────┘
     ↓
Positions / PnL / Audit
```

**Key Principle:** Each stage produces typed outputs consumed by the next. No cross-stage logic.

---

## Component Responsibilities

### 1. Market Data Layer (`polytrader/adapters/`, `polytrader/observer.py`)

**Responsibilities:**
- Connect to Polymarket feeds (WebSocket/REST polling)
- Normalize raw messages into canonical `MarketDataEvent`
- Maintain order book snapshots
- Emit market data events (append-only)

**Key Components:**
- `IMarketDataAdapter` — Protocol for market data ingestion
- `PolymarketMarketDataAdapter` — Polymarket-specific implementation
- `Observer` — Consumes adapter ticks, emits normalized events

**Output:** `MarketDataEvent` (mid, spread, levels, sequence, timestamp)

---

### 2. State Builders (`polytrader/store/`, `polytrader/store_factory.py`)

**Responsibilities:**
- Maintain market snapshots from events
- Provide query interface for current market state
- Support both in-memory and PostgreSQL-backed stores

**Key Components:**
- `IMarketDataStore` — Protocol for market state queries
- `MemoryMarketDataStore` — In-memory implementation
- `PostgresMarketDataStore` — Persistent implementation

**Output:** Market snapshots (current mid, spread, history)

---

### 3. Strategy Layer (`polytrader/strategies/`)

**Responsibilities:**
- Consume normalized market state + positions + config
- Produce **signals** (probabilistic forecasts/scores)
- Deterministic and testable (no side effects)

**Key Components:**
- `IStrategy` — Strategy protocol
- `SimpleThresholdStrategy` — Example threshold-based strategy
- Strategy factories — Create strategy instances from config

**Output:** `SignalEvent` (scores/forecasts, **NOT orders**)

**Rule:** Strategies never produce orders. They produce signals only.

---

### 4. Portfolio Layer (`polytrader/portfolio/`)

**Responsibilities:**
- Convert signals → target positions / order intents
- Apply sizing rules and portfolio constraints
- Generate `OrderIntentEvent` objects

**Key Components:**
- `PortfolioService` — Converts signals to intents
- `Sizing` — Position sizing logic
- `Targets` — Target position calculation

**Output:** `OrderIntentEvent` (side, qty, limit_price, time-in-force)

---

### 5. Risk Layer (`polytrader/risk/`)

**Responsibilities:**
- **Hard gate** for all order intents (pre-trade)
- Enforce limits: max position, max notional, order size, price bands, throttles
- Emit `RiskCheckEvent` (allow/deny + reason codes)

**Key Components:**
- `RiskEngine` — Runs risk policies
- `RiskChecker` — Subscribes to intents, publishes approved proposals
- `RiskPolicies` — Pure rule checks

**Output:** `RiskCheckEvent` (allowed: bool, reasons: list[RiskReasonCode])

**Rule:** Risk is a **veto gate**, never advisory. Denied intents never reach OMS.

---

### 6. OMS (Order Management System) (`polytrader/oms/`)

**Responsibilities:**
- **Sole owner** of order state
- Create idempotency keys (`client_order_id`)
- Track lifecycle: NEW → PENDING_SUBMIT → ACKED → FILLED/CANCELED/REJECTED
- Correlate with venue updates
- Emit order lifecycle events

**Key Components:**
- `OMSCore` — Main OMS orchestrator
- `OrderFSM` — State machine transitions (pure)
- `IOrderStore` — Order state projection
- `IdempotencyStore` — Deduplication

**Output:** `OrderCreatedEvent`, `OrderAckEvent`, `FillEvent`, `OrderCanceledEvent`, etc.

**Rule:** OMS is the **only** writer of order state. All other components read or emit events.

---

### 7. Execution Layer (`polytrader/execution/`)

**Responsibilities:**
- Convert OMS commands → venue-specific actions
- Apply execution tactics (pricing, post-only, throttling)
- Route to venue adapters
- Emit execution events (request/response/latency)

**Key Components:**
- `ExecutionRouter` — Routes commands to adapters
- `ExecutionTactics` — Pricing and order policy
- `IVenueAdapter` — Protocol for venue connectivity

**Output:** Execution logs/events (no state mutation)

**Rule:** Execution never mutates OMS state. It reports outcomes via events.

---

### 8. Venue Adapters (`polytrader/adapters/polymarket/`, `polytrader/execution/`)

**Responsibilities:**
- **IO only** — translate to/from venue APIs
- Handle retries, reconnects, rate limits
- Normalize venue messages → canonical events

**Key Components:**
- `ClobVenueAdapter` — Live trading adapter (Polymarket CLOB API)
- `PaperExecutionAdapter` — Paper trading adapter (simulated execution)

**Output:** Normalized venue events (no business decisions)

**Rule:** Adapters contain **no business logic**. They are pure IO.

---

### 9. Post-Trade (`polytrader/position_manager/`)

**Responsibilities:**
- Maintain positions from `FillEvent` (event-driven)
- Compute realized/unrealized PnL
- Track performance metrics

**Key Components:**
- `IPositionManager` — Position tracking protocol
- `PaperPositionManager` — Paper trading position manager
- `OutcomeTracker` — Track market outcomes
- `PerformanceMetrics` — Calculate performance stats

**Output:** `PositionUpdatedEvent`, `PnLEvent`

**Rule:** Positions are **derived from fills**, not assumptions.

---

### 10. Event System (`polytrader/events/`)

**Responsibilities:**
- Append-only event persistence
- Event bus for pub/sub
- Replay support for debugging

**Key Components:**
- `EventBus` — In-process event bus
- `IEventStore` — Event persistence interface
- `MemoryEventStore` — In-memory implementation
- `PostgresEventStore` — Persistent implementation

**Rule:** All important actions emit immutable events. Replay explains behavior.

---

### 11. Operations & Control (`polytrader/ops/`, `polytrader/api/`)

**Responsibilities:**
- Execution control (enable/disable trading)
- Health checks and circuit breakers
- Control API for operator interaction

**Key Components:**
- `ExecutionControl` — Execution enable/disable
- `HealthChecker` — System health evaluation
- `ControlPlaneService` — Processes control commands
- FastAPI control API — HTTP interface

**Rule:** Default safe state is **execution disabled**.

---

### 12. Platform Orchestration (`polytrader/platform/`)

**Responsibilities:**
- Multi-strategy coordination
- Strategy lifecycle management
- Paper/live lane separation

**Key Components:**
- `PlatformOrchestrator` — Main platform coordinator
- `StrategyRunner` — Per-strategy execution loop
- `MarketSupervisorRegistry` — Shared market supervisors
- `ControlPlaneService` — Control command processing

---

## Live vs Paper Trading

### Paper Trading (Default)

**Execution:**
- Uses `PaperExecutionAdapter` — simulates order execution
- No real API calls to Polymarket
- Deterministic fill simulation based on configurable models
- Tracks positions and PnL in-memory

**Position Management:**
- `PaperPositionManager` — event-driven position tracking
- No external API reconciliation
- Performance metrics calculated from simulated fills

**OMS:**
- Uses `InMemoryOrderStore` — no persistence
- Order state exists only in memory during runtime

**Event Store:**
- Uses `MemoryEventStore` by default (can use PostgreSQL)
- Events are not required for paper trading operation

**Configuration:**
- No API credentials required
- Default mode when no `PRIVATE_KEY` is set

**Use Cases:**
- Strategy development and testing
- Backtesting and validation
- Risk-free experimentation

---

### Live Trading

**Execution:**
- Uses `ClobVenueAdapter` — real Polymarket CLOB API calls
- Requires valid API credentials (`PRIVATE_KEY`, `FUNDER`, `SIGNATURE_TYPE`)
- Real order submission, fills, and cancellations
- Actual capital at risk

**Position Management:**
- Uses `PaperPositionManager` (event-driven from real fills)
- Can be extended with venue reconciliation for production

**OMS:**
- Uses `InMemoryOrderStore` (can be extended with persistent store)
- Order state must handle restart/recovery scenarios

**Event Store:**
- Should use `PostgresEventStore` for audit trail
- Critical for replay and debugging production issues

**Configuration:**
- Requires environment variables:
  - `PRIVATE_KEY` — Polymarket wallet private key
  - `FUNDER` — Magic wallet funder address
  - `SIGNATURE_TYPE` — Signature type (typically `1`)

**Safety:**
- Execution disabled by default (`execution_enabled = false`)
- Requires explicit enable via control API or configuration
- Risk checks are mandatory and cannot be bypassed

**Use Cases:**
- Production trading with real capital
- Requires thorough testing in paper mode first

---

## Component Interaction Flow

### Paper Trading Flow

```
1. Market Data Adapter → MarketDataEvent
2. Observer → Normalized events → Store
3. Strategy → SignalEvent
4. Portfolio → OrderIntentEvent
5. Risk → RiskCheckEvent (allow/deny)
6. OMS → OrderCreatedEvent → SubmitOrderCommand
7. ExecutionRouter → PaperExecutionAdapter
8. PaperExecutionAdapter → FillEvent (simulated)
9. OMS → OrderAckEvent, FillEvent
10. PositionManager → PositionUpdatedEvent, PnLEvent
```

### Live Trading Flow

```
1. Market Data Adapter → MarketDataEvent
2. Observer → Normalized events → Store
3. Strategy → SignalEvent
4. Portfolio → OrderIntentEvent
5. Risk → RiskCheckEvent (allow/deny)
6. OMS → OrderCreatedEvent → SubmitOrderCommand
7. ExecutionRouter → ClobVenueAdapter
8. ClobVenueAdapter → Real API call → Venue response
9. User Stream → Venue order updates → OMS
10. OMS → OrderAckEvent, FillEvent
11. PositionManager → PositionUpdatedEvent, PnLEvent
```

**Key Difference:** Step 7-8 — Paper uses simulated execution, Live uses real API calls.

---

## Data Flow Contracts

All inter-component communication uses **typed models**, never raw dicts:

- **Events:** Immutable facts (append-only)
  - `MarketDataEvent`, `SignalEvent`, `OrderIntentEvent`, `RiskCheckEvent`, `OrderCreatedEvent`, `FillEvent`, etc.

- **Commands:** Requests to do something
  - `SubmitOrderCommand`, `CancelOrderCommand`

- **Queries:** Read-only projections
  - Market snapshots, order state, positions

---

## Safety & Risk Controls

### Default Safe State
- `execution_enabled = false` (no trading)
- Execution requires explicit enable via control API

### Risk Gates
- **Pre-trade risk:** All intents must pass risk checks
- **Hard veto:** Denied intents never reach OMS
- **Reason codes:** All denials include explicit reasons

### Circuit Breakers
- Market data staleness
- Reconciliation divergence
- Error rate thresholds
- Latency breaches

### Observability
- All actions emit events (audit trail)
- Structured logging with correlation IDs
- Metrics for key operations (Prometheus-compatible)
- Replay support for debugging

**Metrics Infrastructure:**
- Dedicated metrics server on port 9100 (separate from control API on port 8000)
- Prometheus metrics collector (default) for operator visibility via Grafana
- Metrics exposed at `http://localhost:9100/metrics` in Prometheus format
- All metrics follow `observability.mdc` §4 specifications (market data, strategy, risk, OMS, posttrade, safety)

---

## Non-Negotiable Principles

1. **Strategy produces signals, not orders**
2. **Risk is a hard gate before OMS submission**
3. **OMS is the sole owner of order state**
4. **Adapters are IO only, no business logic**
5. **Everything emits events; replay explains behavior**
6. **Default safe mode is execution disabled**

---

## Repository Structure

```
polytrader/
├── adapters/          # Market data and venue adapters
├── api/              # Control API (FastAPI)
├── common/           # Shared primitives (IDs, types)
├── events/           # Event bus, store, types
├── execution/        # Execution router, tactics, adapters
├── market_discovery/ # Market discovery service
├── observer.py       # Market data observer
├── oms/              # Order Management System (CORE)
├── ops/              # Operations control, health
├── platform/         # Multi-strategy orchestration
├── portfolio/        # Portfolio construction, sizing
├── position_manager/ # Position tracking, PnL
├── risk/             # Pre-trade risk engine
├── strategies/       # Trading strategies
├── supervisor/       # Component lifecycle management
└── tasks/            # Platform startup tasks
```

---

## Further Reading

- `.cursor/rules/architecture.mdc` — Detailed module boundaries
- `.cursor/rules/flows.mdc` — Canonical trading flows
- `.cursor/rules/trading.mdc` — Trading-specific rules
- `.cursor/rules/observability.mdc` — Event schemas and metrics
- `docs/GETTING_STARTED.md` — Setup and usage guide
