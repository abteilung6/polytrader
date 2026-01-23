# Test Folder Structure Analysis — Polytrader

**Date:** 2025-01-27  
**Status:** Analysis (Not Implemented)  
**Goal:** Understand current test organization and identify inconsistencies

---

## Executive Summary

The `tests/` directory has **mixed organization patterns**:

- **36 test files** at root level (`tests/test_*.py`)
- **13 test files** in `tests/unit/` (properly organized)
- **46 test files** in `tests/integration/` (properly organized)
- **22 test files** in domain-specific folders (`adapters/`, `execution/`, `portfolio/`, etc.)

**Key Issues:**
1. Many unit tests are at root level instead of `tests/unit/`
2. Some integration tests are at root level (e.g., `test_events_bus_store_integration.py`)
3. Domain-specific folders mix unit and integration concerns
4. Inconsistent use of pytest markers (`@pytest.mark.integration`)

---

## Current Structure Breakdown

### 1. Root Level (`tests/test_*.py`) — 36 files

**Files that should be in `tests/unit/`:**

| File | Type | Reason |
|------|------|--------|
| `test_oms_fsm.py` | Unit | Pure FSM logic, no I/O |
| `test_oms_models.py` | Unit | Model validation, no I/O |
| `test_oms_idempotency.py` | Unit | Pure logic, no I/O |
| `test_oms_store.py` | Unit | In-memory store, no DB |
| `test_oms_reconcile.py` | Unit | Uses FakeVenueAdapter, no real DB |
| `test_oms_core.py` | Unit | Uses fixtures, no real DB |
| `test_oms_core_user_stream.py` | Unit | Uses mocks, no real DB |
| `test_oms_edge_cases.py` | Unit | Edge case logic, no I/O |
| `test_risk_engine.py` | Unit | Pure risk logic, no I/O |
| `test_risk_models.py` | Unit | Model validation |
| `test_risk_policies.py` | Unit | Policy logic, no I/O |
| `test_risk_policies_position.py` | Unit | Policy logic, no I/O |
| `test_risk_policies_price_freshness.py` | Unit | Policy logic, no I/O |
| `test_risk_policies_system_health.py` | Unit | Policy logic, no I/O |
| `test_risk_logging.py` | Unit | Logging tests, no I/O |
| `test_risk_metrics.py` | Unit | Metrics tests, no I/O |
| `test_ops_circuit_breaker.py` | Unit | Circuit breaker logic |
| `test_ops_health.py` | Unit | Health check logic |
| `test_events.py` | Unit | Event model tests |
| `test_events_types.py` | Unit | Event type tests |
| `test_events_store.py` | Unit | In-memory store tests |
| `test_events_lifecycle.py` | Unit | Event lifecycle logic |
| `test_config_loading.py` | Unit | Config parsing, no I/O |
| `test_common_ids.py` | Unit | ID generation logic |
| `test_store.py` | Unit | Generic store tests |
| `test_observer.py` | Unit | Observer pattern tests |
| `test_market_pattern.py` | Unit | Pattern matching logic |
| `test_market_supervisor.py` | Unit | Supervisor logic (may need verification) |
| `test_system_supervisor.py` | Unit | Supervisor logic (may need verification) |
| `test_signal_target_events.py` | Unit | Event model tests |
| `test_position_manager.py` | Unit | Position manager logic (may need verification) |

**Files that should be in `tests/integration/`:**

| File | Type | Reason |
|------|------|--------|
| `test_events_bus_store_integration.py` | Integration | Tests EventBus + EventStore integration |
| `test_risk_metrics_integration.py` | Integration | Tests risk metrics emission (per docstring) |
| `test_ops_replay.py` | Integration/Replay | State reconstruction from events (replay test) |

**Files that are ambiguous (need review):**

| File | Type | Notes |
|------|------|-------|
| `test_risk_checker_max_trades_race.py` | ? | Race condition test - may be integration |
| `test_risk_limits_store.py` | ? | May use DB - needs verification |

---

### 2. Unit Tests (`tests/unit/`) — 13 files

**Current structure:**
```
tests/unit/
├── events/
│   └── test_order_intent_event.py
├── execution/
│   └── test_execution_router_strategy_check.py
├── oms/
│   └── conftest.py (fixtures)
├── platform/
│   ├── test_per_strategy_performance.py
│   ├── test_strategy_runner_shared_supervisor.py
│   └── test_supervisor_registry.py
├── portfolio/
│   └── test_intents.py
├── risk/
│   ├── conftest.py (fixtures)
│   ├── test_risk_engine_strategy_activation.py
│   └── test_strategy_activation_policy.py
├── supervisor/
│   └── test_market_supervisor_strategy_less.py
├── test_event_serialization.py
├── test_obs_logging.py
├── test_obs_metrics.py
└── test_tick_writer.py
```

**Observations:**
- ✅ Good: Module-specific organization (`unit/oms/`, `unit/risk/`, etc.)
- ✅ Good: Has `conftest.py` files for module-specific fixtures
- ⚠️ Issue: Some files at root of `unit/` (should be in subdirectories)

---

### 3. Integration Tests (`tests/integration/`) — 46 files

**Current structure:**
```
tests/integration/
├── conftest.py (DB fixtures)
├── test_*_metrics.py (various metrics tests)
├── test_*_logging.py (various logging tests)
├── test_db_*.py (database tests)
├── test_postgres_*.py (PostgreSQL-specific tests)
├── test_platform_orchestrator*.py (platform integration)
├── test_oms_*.py (OMS integration)
├── test_*_pipeline.py (pipeline integration)
└── ... (many more)
```

**Observations:**
- ✅ Good: Clear separation from unit tests
- ✅ Good: Has `conftest.py` for DB fixtures
- ✅ Good: Uses `@pytest.mark.integration` markers (7 files)
- ⚠️ Issue: Not all integration tests use the marker

---

### 4. Domain-Specific Folders — 22 files

**Structure:**
```
tests/
├── adapters/ (2 files)
│   ├── test_polymarket_canonical_models.py
│   └── test_polymarket_user_stream.py
├── execution/ (3 files)
│   ├── test_adapter_protocol.py
│   ├── test_fill_models.py
│   └── test_paper_adapter.py
├── market_discovery/ (5 files)
│   ├── test_market_state_validation.py
│   ├── test_metrics.py
│   ├── test_patterns.py
│   ├── test_service.py
│   └── test_start_convention.py
├── portfolio/ (5 files)
│   ├── test_intents.py
│   ├── test_models.py
│   ├── test_service.py
│   ├── test_sizing.py
│   └── test_targets.py
├── position_manager/ (4 files)
│   ├── test_outcome_tracker.py
│   ├── test_paper_market_change.py
│   ├── test_paper_unrealized_pnl.py
│   └── test_performance_metrics.py
├── strategies/ (2 files)
│   ├── simple_threshold/
│   │   └── test_strategy.py
│   └── test_base.py
└── tasks/ (1 file)
    └── test_builders.py
```

**Observations:**
- ⚠️ **Mixed concerns:** These folders contain both unit and integration tests
- ⚠️ **Inconsistent:** Some domain tests are in `tests/unit/` (e.g., `unit/portfolio/test_intents.py`), others are in `tests/portfolio/`
- ⚠️ **Unclear:** No clear pattern for when to use domain folders vs. `unit/` or `integration/`

---

## Classification Issues

### Issue 1: Root-Level Unit Tests

**Problem:** 30+ unit test files at root level should be in `tests/unit/`

**Examples:**
- `test_oms_fsm.py` → should be `tests/unit/oms/test_fsm.py`
- `test_risk_engine.py` → should be `tests/unit/risk/test_engine.py`
- `test_events_types.py` → should be `tests/unit/events/test_types.py`

**Impact:**
- Harder to find related tests
- Inconsistent with existing `tests/unit/` structure
- Violates testing.mdc organization principles

---

### Issue 2: Integration Tests at Root

**Problem:** Some integration tests are at root level

**Examples:**
- `test_events_bus_store_integration.py` → should be `tests/integration/test_events_bus_store.py`
- `test_risk_metrics_integration.py` → should be `tests/integration/test_risk_metrics.py`
- `test_ops_replay.py` → should be `tests/integration/test_ops_replay.py` or `tests/replay/test_ops_replay.py`

**Impact:**
- Unclear test type without reading file
- Inconsistent with `tests/integration/` structure

---

### Issue 3: Domain Folders vs. Unit/Integration

**Problem:** Domain-specific folders (`tests/portfolio/`, `tests/execution/`, etc.) mix unit and integration concerns

**Examples:**
- `tests/portfolio/test_intents.py` (unit test) vs. `tests/unit/portfolio/test_intents.py` (also exists?)
- `tests/execution/test_paper_adapter.py` (may be integration)
- `tests/position_manager/test_paper_unrealized_pnl.py` (may be integration)

**Questions:**
1. Should domain folders be removed in favor of `tests/unit/` and `tests/integration/`?
2. Or should domain folders mirror source structure (`tests/portfolio/` → `polytrader/portfolio/`)?

---

### Issue 4: Pytest Markers

**Current state:**
- Only 7 files use `@pytest.mark.integration`
- No files use `@pytest.mark.replay` (despite `test_ops_replay.py` existing)
- Note: `@pytest.mark.unit` is not needed (unit tests are default)

**Impact:**
- Cannot easily filter tests by type
- Inconsistent with registered markers in `pyproject.toml`

---

## Recommended Organization (Per testing.mdc)

Per `.cursor/rules/testing.mdc` §4:

```
tests/
├── unit/              # Fast, deterministic, no I/O
│   ├── alpha/
│   ├── portfolio/
│   ├── risk/
│   ├── oms/
│   ├── md/
│   └── ...
├── integration/        # Bounded, realistic, may use DB/fakes
│   ├── pipeline_dry_run_test.py
│   ├── user_stream_handling_test.py
│   └── reconcile_test.py
└── replay/            # Golden tests, event log replay
    ├── test_replay_golden_*.py
    └── fixtures/
        └── event_log_*.jsonl
```

**Current vs. Recommended:**

| Current | Recommended | Action |
|---------|-------------|--------|
| `tests/test_oms_fsm.py` | `tests/unit/oms/test_fsm.py` | Move |
| `tests/test_risk_engine.py` | `tests/unit/risk/test_engine.py` | Move |
| `tests/test_events_types.py` | `tests/unit/events/test_types.py` | Move |
| `tests/test_events_bus_store_integration.py` | `tests/integration/test_events_bus_store.py` | Move |
| `tests/test_ops_replay.py` | `tests/replay/test_ops_replay.py` | Move |
| `tests/portfolio/test_intents.py` | `tests/unit/portfolio/test_intents.py` | Move |
| `tests/execution/test_paper_adapter.py` | `tests/integration/test_execution_paper_adapter.py` | Move (if integration) |

---

## Migration Complexity

### Low Risk (Simple Moves)
- Moving root-level unit tests to `tests/unit/`
- Moving root-level integration tests to `tests/integration/`
- Updating imports (if needed)

### Medium Risk (Requires Review)
- Determining if domain folder tests are unit or integration
- Consolidating duplicate tests (e.g., `tests/portfolio/` vs. `tests/unit/portfolio/`)
- Adding pytest markers consistently

### High Risk (Requires Careful Planning)
- Creating `tests/replay/` directory structure
- Moving replay tests
- Ensuring all imports still work after moves

---

## Statistics Summary

| Category | Count | Location |
|----------|-------|----------|
| **Root-level tests** | 36 | `tests/test_*.py` |
| **Unit tests (organized)** | 13 | `tests/unit/` |
| **Integration tests (organized)** | 46 | `tests/integration/` |
| **Domain folder tests** | 22 | `tests/{adapters,execution,portfolio,...}/` |
| **Total test files** | 117 | (excluding conftest, factories) |
| **Files with `@pytest.mark.integration`** | 7 | All in `tests/integration/` |
| **Files with `@pytest.mark.replay`** | 0 | None found |

---

## Implementation Plan: Commit Structure

This section organizes the reorganization into logical commits that can be implemented incrementally.

### Commit Group 1: Move OMS Unit Tests (Low Risk)

**Commit 1.1: Move OMS FSM tests to unit directory**
- Files: `tests/test_oms_fsm.py` → `tests/unit/oms/test_fsm.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/oms/test_fsm.py -v` passes

**Commit 1.2: Move OMS models tests to unit directory**
- Files: `tests/test_oms_models.py` → `tests/unit/oms/test_models.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/oms/test_models.py -v` passes

**Commit 1.3: Move OMS store tests to unit directory**
- Files: `tests/test_oms_store.py` → `tests/unit/oms/test_store.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/oms/test_store.py -v` passes

**Commit 1.4: Move OMS idempotency tests to unit directory**
- Files: `tests/test_oms_idempotency.py` → `tests/unit/oms/test_idempotency.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/oms/test_idempotency.py -v` passes

**Commit 1.5: Move OMS reconcile tests to unit directory**
- Files: `tests/test_oms_reconcile.py` → `tests/unit/oms/test_reconcile.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/oms/test_reconcile.py -v` passes

**Commit 1.6: Move OMS core tests to unit directory**
- Files: `tests/test_oms_core.py` → `tests/unit/oms/test_core.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/oms/test_core.py -v` passes

**Commit 1.7: Move OMS core user stream tests to unit directory**
- Files: `tests/test_oms_core_user_stream.py` → `tests/unit/oms/test_core_user_stream.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/oms/test_core_user_stream.py -v` passes

**Commit 1.8: Move OMS edge cases tests to unit directory**
- Files: `tests/test_oms_edge_cases.py` → `tests/unit/oms/test_edge_cases.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/oms/test_edge_cases.py -v` passes

---

### Commit Group 2: Move Risk Unit Tests (Low Risk)

**Commit 2.1: Move risk engine tests to unit directory**
- Files: `tests/test_risk_engine.py` → `tests/unit/risk/test_engine.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/risk/test_engine.py -v` passes

**Commit 2.2: Move risk models tests to unit directory**
- Files: `tests/test_risk_models.py` → `tests/unit/risk/test_models.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/risk/test_models.py -v` passes

**Commit 2.3: Move risk policies tests to unit directory**
- Files: `tests/test_risk_policies.py` → `tests/unit/risk/test_policies.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/risk/test_policies.py -v` passes

**Commit 2.4: Move risk policy position tests to unit directory**
- Files: `tests/test_risk_policies_position.py` → `tests/unit/risk/test_policies_position.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/risk/test_policies_position.py -v` passes

**Commit 2.5: Move risk policy price freshness tests to unit directory**
- Files: `tests/test_risk_policies_price_freshness.py` → `tests/unit/risk/test_policies_price_freshness.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/risk/test_policies_price_freshness.py -v` passes

**Commit 2.6: Move risk policy system health tests to unit directory**
- Files: `tests/test_risk_policies_system_health.py` → `tests/unit/risk/test_policies_system_health.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/risk/test_policies_system_health.py -v` passes

**Commit 2.7: Move risk logging tests to unit directory**
- Files: `tests/test_risk_logging.py` → `tests/unit/risk/test_logging.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/risk/test_logging.py -v` passes

**Commit 2.8: Move risk metrics tests to unit directory**
- Files: `tests/test_risk_metrics.py` → `tests/unit/risk/test_metrics.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/risk/test_metrics.py -v` passes

**Commit 2.9: Move risk limits store tests (review needed)**
- Files: `tests/test_risk_limits_store.py` → `tests/unit/risk/test_limits_store.py` OR `tests/integration/test_risk_limits_store.py`
- Changes: Move file, classify as unit or integration, update imports
- Verification: Run tests and verify classification

---

### Commit Group 3: Move Events Unit Tests (Low Risk)

**Commit 3.1: Move events types tests to unit directory**
- Files: `tests/test_events_types.py` → `tests/unit/events/test_types.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/events/test_types.py -v` passes

**Commit 3.2: Move events store tests to unit directory**
- Files: `tests/test_events_store.py` → `tests/unit/events/test_store.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/events/test_store.py -v` passes

**Commit 3.3: Move events lifecycle tests to unit directory**
- Files: `tests/test_events_lifecycle.py` → `tests/unit/events/test_lifecycle.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/events/test_lifecycle.py -v` passes

**Commit 3.4: Move events tests to unit directory**
- Files: `tests/test_events.py` → `tests/unit/events/test_events.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/events/test_events.py -v` passes

**Commit 3.5: Move signal target events tests to unit directory**
- Files: `tests/test_signal_target_events.py` → `tests/unit/events/test_signal_target.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/events/test_signal_target.py -v` passes

---

### Commit Group 4: Move Ops Unit Tests (Low Risk)

**Commit 4.1: Move ops circuit breaker tests to unit directory**
- Files: `tests/test_ops_circuit_breaker.py` → `tests/unit/ops/test_circuit_breaker.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/ops/test_circuit_breaker.py -v` passes

**Commit 4.2: Move ops health tests to unit directory**
- Files: `tests/test_ops_health.py` → `tests/unit/ops/test_health.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/ops/test_health.py -v` passes

---

### Commit Group 5: Move Root-Level Integration Tests (Low Risk)

**Commit 5.1: Move events bus store integration tests**
- Files: `tests/test_events_bus_store_integration.py` → `tests/integration/test_events_bus_store.py`
- Changes: Move file, add `@pytest.mark.integration` marker, update imports
- Verification: `pytest tests/integration/test_events_bus_store.py -v` passes

**Commit 5.2: Move risk metrics integration tests**
- Files: `tests/test_risk_metrics_integration.py` → `tests/integration/test_risk_metrics.py`
- Changes: Move file, add `@pytest.mark.integration` marker, update imports
- Verification: `pytest tests/integration/test_risk_metrics.py -v` passes

---

### Commit Group 6: Create Replay Directory and Move Replay Tests (Low Risk)

**Commit 6.1: Create replay directory structure**
- Files: Create `tests/replay/` directory and `tests/replay/fixtures/` subdirectory
- Changes: Create directory structure
- Verification: Directories exist

**Commit 6.2: Move ops replay tests to replay directory**
- Files: `tests/test_ops_replay.py` → `tests/replay/test_ops_replay.py`
- Changes: Move file, add `@pytest.mark.replay` marker, update imports
- Verification: `pytest tests/replay/test_ops_replay.py -v` passes

---

### Commit Group 7: Move Remaining Root-Level Unit Tests (Low Risk)

**Commit 7.1: Move config loading tests to unit directory**
- Files: `tests/test_config_loading.py` → `tests/unit/test_config_loading.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/test_config_loading.py -v` passes

**Commit 7.2: Move common IDs tests to unit directory**
- Files: `tests/test_common_ids.py` → `tests/unit/test_common_ids.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/test_common_ids.py -v` passes

**Commit 7.3: Move store tests to unit directory**
- Files: `tests/test_store.py` → `tests/unit/test_store.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/test_store.py -v` passes

**Commit 7.4: Move observer tests to unit directory**
- Files: `tests/test_observer.py` → `tests/unit/test_observer.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/test_observer.py -v` passes

**Commit 7.5: Move market pattern tests to unit directory**
- Files: `tests/test_market_pattern.py` → `tests/unit/test_market_pattern.py`
- Changes: Move file, update imports if needed
- Verification: `pytest tests/unit/test_market_pattern.py -v` passes

**Commit 7.6: Move market supervisor tests (review needed)**
- Files: `tests/test_market_supervisor.py` → `tests/unit/supervisor/test_market_supervisor.py` OR `tests/integration/test_market_supervisor.py`
- Changes: Move file, classify as unit or integration, update imports
- Verification: Run tests and verify classification

**Commit 7.7: Move system supervisor tests (review needed)**
- Files: `tests/test_system_supervisor.py` → `tests/unit/supervisor/test_system_supervisor.py` OR `tests/integration/test_system_supervisor.py`
- Changes: Move file, classify as unit or integration, update imports
- Verification: Run tests and verify classification

**Commit 7.8: Move position manager tests (review needed)**
- Files: `tests/test_position_manager.py` → `tests/unit/position_manager/test_position_manager.py` OR `tests/integration/test_position_manager.py`
- Changes: Move file, classify as unit or integration, update imports
- Verification: Run tests and verify classification

**Commit 7.9: Move risk checker max trades race tests (review needed)**
- Files: `tests/test_risk_checker_max_trades_race.py` → `tests/unit/risk/test_checker_max_trades_race.py` OR `tests/integration/test_risk_checker_max_trades_race.py`
- Changes: Move file, classify as unit or integration, update imports
- Verification: Run tests and verify classification

---

### Commit Group 8: Consolidate Domain Folders - Portfolio (Medium Risk)

**Commit 8.1: Review and move portfolio tests**
- Files: Review `tests/portfolio/*.py` and move to appropriate location
  - `tests/portfolio/test_intents.py` → `tests/unit/portfolio/test_intents.py` (if unit) OR remove if duplicate
  - `tests/portfolio/test_models.py` → `tests/unit/portfolio/test_models.py`
  - `tests/portfolio/test_service.py` → Classify and move to `tests/unit/portfolio/` or `tests/integration/`
  - `tests/portfolio/test_sizing.py` → `tests/unit/portfolio/test_sizing.py`
  - `tests/portfolio/test_targets.py` → `tests/unit/portfolio/test_targets.py`
- Changes: Review each file, classify, move, update imports, remove duplicates
- Verification: All tests pass, no duplicate test files

---

### Commit Group 9: Consolidate Domain Folders - Execution (Medium Risk)

**Commit 9.1: Review and move execution tests**
- Files: Review `tests/execution/*.py` and move to appropriate location
  - `tests/execution/test_adapter_protocol.py` → `tests/unit/execution/test_adapter_protocol.py`
  - `tests/execution/test_fill_models.py` → `tests/unit/execution/test_fill_models.py`
  - `tests/execution/test_paper_adapter.py` → Classify and move to `tests/unit/execution/` or `tests/integration/`
- Changes: Review each file, classify, move, update imports
- Verification: All tests pass

---

### Commit Group 10: Consolidate Domain Folders - Adapters (Medium Risk)

**Commit 10.1: Review and move adapter tests**
- Files: Review `tests/adapters/*.py` and move to appropriate location
  - `tests/adapters/test_polymarket_canonical_models.py` → `tests/unit/adapters/test_polymarket_canonical_models.py`
  - `tests/adapters/test_polymarket_user_stream.py` → Classify and move to `tests/unit/adapters/` or `tests/integration/`
- Changes: Review each file, classify, move, update imports
- Verification: All tests pass

---

### Commit Group 11: Consolidate Domain Folders - Remaining (Medium Risk)

**Commit 11.1: Review and move market discovery tests**
- Files: Review `tests/market_discovery/*.py` and move to appropriate location
- Changes: Classify each as unit or integration, move, update imports
- Verification: All tests pass

**Commit 11.2: Review and move position manager tests**
- Files: Review `tests/position_manager/*.py` and move to appropriate location
- Changes: Classify each as unit or integration, move, update imports
- Verification: All tests pass

**Commit 11.3: Review and move strategies tests**
- Files: Review `tests/strategies/*.py` and move to appropriate location
- Changes: Classify each as unit or integration, move, update imports
- Verification: All tests pass

**Commit 11.4: Review and move tasks tests**
- Files: Review `tests/tasks/*.py` and move to appropriate location
- Changes: Classify each as unit or integration, move, update imports
- Verification: All tests pass

---

### Commit Group 12: Add Integration Markers Consistently (Low Risk)

**Commit 12.1: Add integration markers to all integration tests**
- Files: All files in `tests/integration/` that don't have `@pytest.mark.integration`
- Changes: Add `@pytest.mark.integration` marker to test classes or functions
- Verification: `pytest -m "not integration"` skips all integration tests

---

### Commit Group 13: Cleanup Empty Directories (Low Risk)

**Commit 13.1: Remove empty domain directories**
- Files: Remove empty directories after all tests moved
- Changes: Remove `tests/portfolio/`, `tests/execution/`, etc. if empty
- Verification: No empty test directories remain

---

## Commit Execution Rules

**For each commit:**
1. ✅ Run `make format` to ensure code formatting
2. ✅ Run `make lint` to check for linting errors
3. ✅ Run `make type-check` to verify type safety
4. ✅ Run `pytest <moved_file> -v` to verify tests pass
5. ✅ Run `make test` to ensure no regressions
6. ✅ Commit with single-sentence message (e.g., "Move OMS FSM tests to unit directory")

**Commit message format:**
- Single sentence, no additional description
- Example: "Move OMS FSM tests to unit directory"
- Example: "Move risk engine tests to unit directory"
- Example: "Add integration markers to integration tests"

**Verification commands:**
```bash
# After each move:
pytest tests/unit/oms/test_fsm.py -v  # Verify moved test works
make format && make lint && make type-check && make test  # Full check
```

---

## Open Questions

1. **Domain folders:** Should we keep `tests/portfolio/`, `tests/execution/`, etc., or move everything to `tests/unit/` and `tests/integration/`?

2. **Module structure:** Should `tests/unit/oms/` mirror `polytrader/oms/` exactly, or use a flatter structure?

3. **Replay tests:** Should replay tests be in `tests/integration/` or separate `tests/replay/` directory?

4. **Fixtures:** Should domain-specific fixtures (e.g., `tests/unit/oms/conftest.py`) be kept, or consolidated?

5. **Naming:** Should we rename files to match source structure? (e.g., `test_oms_fsm.py` → `test_fsm.py` when in `tests/unit/oms/`)

---

## References

- `.cursor/rules/testing.mdc` §4 — Test Categories & Folder Structure
- `.cursor/rules/unit_testing_techinical.mdc` — Unit test guidelines
- `docs/Test_Code_Cleanup_Proposal.md` — Related cleanup proposal

---

**End of Analysis**
