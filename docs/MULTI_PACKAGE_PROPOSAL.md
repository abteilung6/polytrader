# Multi-Package Monorepo Proposal — Polytrader

**Status:** Proposal  
**Date:** 2025-01-27  
**Author:** Architecture Review

---

## Executive Summary

This document proposes splitting the current single-package monolith (`polytrader/`) into multiple Python packages within the same repository. This aligns with institutional trading system best practices and addresses current architectural pain points while preserving monorepo benefits.

**Recommendation:** Proceed with multi-package structure at current scale.

---

## What Elite Companies Do

### Institutional Trading Firms (Citadel, Jane Street, Jump)

- **Monorepo-first approach**: Single repository with multiple packages/services
- **Clear dependency boundaries**: Packages enforce architectural layers
- **Independent versioning**: Each package can evolve independently while maintaining compatibility
- **Shared tooling**: Unified linting, testing, and CI/CD across packages
- **"Living at HEAD"**: Internal packages depend on latest code, not published versions

### Tech Companies (Dropbox, Opendoor)

- **Dropbox**: Evolved from monolith to managed platform, but maintains monorepo structure
- **Opendoor**: Consolidated multiple services into one monorepo to eliminate coordination friction
- **Key insight**: "Monolith should be by choice"—structure supports both monolithic deployment and future service split

---

## Current State Analysis

### Strengths
- Clear architectural boundaries (risk, oms, execution, events, etc.)
- Well-defined module structure
- Single deployment unit (simplifies operations)

### Pain Points
- **Circular import issues**: Evidence of workarounds (lazy imports, `__getattr__`)
- **Tight coupling**: Modules can import across boundaries without enforcement
- **No dependency isolation**: All modules share same namespace
- **Testing complexity**: Hard to test packages in isolation
- **Future migration risk**: Moving to multi-process later requires refactoring

### Evidence from Codebase
```python
# polytrader/adapters/__init__.py (lines 46-48)
# "We need to import the module file directly to avoid circular import"
# "The package polymarket/__init__.py imports from market_data, which would
# cause a circular import if we import the package"
```

```python
# polytrader/events/__init__.py (lines 124-180)
# def __getattr__(name: str):
#     """Lazily import topic constants from topics module.
#     This defers topic initialization until after all modules are fully loaded,
#     breaking the circular import between polytrader.types and polytrader.events.
```

---

## Proposed Structure

### Package Hierarchy (Dependency Flow)

```
polytrader-core/          # Foundation (no dependencies on other packages)
  ├── common/            # IDs, types, clock, errors
  ├── events/            # Event bus, types, store
  └── config/            # Configuration loading

polytrader-md/           # Market Data (depends on core)
  ├── adapters/          # Venue adapters (IO only)
  ├── normalization/     # Raw → canonical
  └── book/              # Order book state

polytrader-alpha/        # Signal Generation (depends on core, md)
  └── strategies/        # Strategy implementations

polytrader-portfolio/    # Portfolio Construction (depends on core, alpha)
  ├── targets/           # Target exposure computation
  ├── sizing/            # Position sizing
  └── intents/           # OrderIntent generation

polytrader-risk/         # Pre-Trade Risk (depends on core, portfolio)
  ├── policies/          # Pure risk rules
  └── engine/            # Policy orchestration

polytrader-oms/          # Order Management (depends on core, risk)
  ├── models/            # Order, Fill models
  ├── fsm/               # State machine
  └── reconcile/         # Venue reconciliation

polytrader-execution/    # Execution Layer (depends on core, oms)
  ├── router/            # Order routing
  ├── tactics/           # Execution tactics
  └── pricing/           # Limit price rules

polytrader-posttrade/    # Post-Trade (depends on core, oms)
  ├── positions/         # Position tracking
  └── pnl/               # PnL computation

polytrader-obs/          # Observability (depends on core)
  ├── logging/           # Structured logging
  ├── metrics/           # Metrics collection
  └── tracing/           # Distributed tracing

polytrader-ops/          # Operations (depends on core, obs)
  ├── control/           # Kill switch, flags
  └── health/            # Health checks

polytrader-platform/     # Orchestration (depends on all)
  ├── supervisor/        # Component lifecycle
  └── tasks/             # Startup tasks
```

### Directory Structure

```
polytrader/
├── pyproject.toml                    # Root workspace config
├── packages/
│   ├── core/
│   │   ├── pyproject.toml           # Package metadata
│   │   ├── src/
│   │   │   └── polytrader_core/
│   │   │       ├── common/
│   │   │       ├── events/
│   │   │       └── config/
│   │   └── tests/
│   ├── md/
│   │   ├── pyproject.tomn
│   │   ├── src/
│   │   │   └── polytrader_md/
│   │   └── tests/
│   ├── alpha/
│   ├── portfolio/
│   ├── risk/
│   ├── oms/
│   ├── execution/
│   ├── posttrade/
│   ├── obs/
│   ├── ops/
│   └── platform/
├── tests/                            # Integration tests (cross-package)
└── docs/
```

### Package Naming Convention

- **Internal packages**: `polytrader-{component}` (e.g., `polytrader-core`, `polytrader-risk`)
- **Import names**: `polytrader_{component}` (e.g., `polytrader_core`, `polytrader_risk`)
- **Rationale**: Hyphens for package names (filesystem), underscores for imports (Python)

---

## Advantages

### 1. **Dependency Enforcement**
- **Current**: Any module can import from any other module
- **Proposed**: Package dependencies are explicit in `pyproject.toml`
- **Benefit**: Prevents architectural violations (e.g., strategy importing adapters)

### 2. **Eliminates Circular Dependencies**
- **Current**: Workarounds with lazy imports and `__getattr__`
- **Proposed**: Clear dependency graph enforced by package system
- **Benefit**: Cleaner imports, faster startup, better IDE support

### 3. **Independent Testing**
- **Current**: All modules tested together
- **Proposed**: Each package has isolated test suite
- **Benefit**: Faster feedback, clearer test boundaries

### 4. **Future-Proof Architecture**
- **Current**: Single-process deployment only
- **Proposed**: Packages can be split into services later without code changes
- **Benefit**: Mechanical migration path (per `architecture.mdc` §3)

### 5. **Versioning Flexibility**
- **Current**: Single version for entire system
- **Proposed**: Each package can version independently (if needed)
- **Benefit**: Gradual rollout, A/B testing of components

### 6. **Clearer Ownership**
- **Current**: Module boundaries are organizational, not enforced
- **Proposed**: Package boundaries are technical and enforced
- **Benefit**: Easier code reviews, clearer responsibilities

### 7. **Better IDE Support**
- **Current**: Large namespace, slow autocomplete
- **Proposed**: Smaller, focused packages
- **Benefit**: Faster IDE indexing, better navigation

### 8. **Selective Installation**
- **Current**: Must install entire system
- **Proposed**: Install only needed packages (e.g., for testing)
- **Benefit**: Faster CI, smaller Docker images

---

## Tradeoffs & Considerations

### Disadvantages

1. **Initial Migration Cost**
   - Requires refactoring imports across codebase
   - Estimated effort: 2-3 days for careful migration
   - **Mitigation**: Incremental migration (one package at a time)

2. **Slightly More Complex Setup**
   - Multiple `pyproject.toml` files to maintain
   - **Mitigation**: Use workspace tooling (poetry, uv, or hatch)

3. **Potential Over-Engineering**
   - If system remains small, packages may be unnecessary
   - **Assessment**: Current codebase already shows architectural boundaries; packages formalize existing structure

### When to Reconsider

- **If system shrinks**: If codebase reduces significantly, consider reverting
- **If deployment changes**: If moving to microservices, packages become services
- **If team is very small**: Single package may be simpler for 1-2 person teams

**Current assessment**: System is at right scale for multi-package structure.

---

## Implementation Plan

### Phase 1: Setup Workspace (1 day)
1. Install workspace tooling (recommend `uv` or `poetry` workspaces)
2. Create `packages/` directory structure
3. Configure root `pyproject.toml` as workspace

### Phase 2: Extract Core Package (1 day)
1. Move `common/`, `events/`, `config/` to `polytrader-core`
2. Update imports: `polytrader.common` → `polytrader_core.common`
3. Verify tests pass

### Phase 3: Extract Leaf Packages (2 days)
1. Extract `obs/` → `polytrader-obs` (depends on core)
2. Extract `md/` → `polytrader-md` (depends on core)
3. Extract `posttrade/` → `polytrader-posttrade` (depends on core, oms)

### Phase 4: Extract Pipeline Packages (3 days)
1. Extract `alpha/` → `polytrader-alpha` (depends on core, md)
2. Extract `portfolio/` → `polytrader-portfolio` (depends on core, alpha)
3. Extract `risk/` → `polytrader-risk` (depends on core, portfolio)
4. Extract `oms/` → `polytrader-oms` (depends on core, risk)
5. Extract `execution/` → `polytrader-execution` (depends on core, oms)

### Phase 5: Extract Platform (1 day)
1. Extract `platform/`, `supervisor/`, `tasks/` → `polytrader-platform`
2. Update entry points (`cli.py`, `api/`)

### Phase 6: Cleanup (1 day)
1. Remove old `polytrader/` package structure
2. Update documentation
3. Verify full system tests pass

**Total estimated time**: 8-10 days (can be done incrementally)

---

## Tooling Recommendations

### Option 1: UV Workspaces (Recommended)
```toml
# pyproject.toml (root)
[tool.uv.workspace]
members = ["packages/*"]
```

**Pros**: Fast, modern, simple  
**Cons**: Newer tool (but stable)

### Option 2: Poetry Workspaces
```toml
# pyproject.toml (root)
[tool.poetry]
packages = [{include = "packages/*"}]
```

**Pros**: Mature, widely used  
**Cons**: Slower than uv

### Option 3: Hatch Workspaces
```toml
# pyproject.toml (root)
[tool.hatch.build.targets.wheel]
packages = ["packages"]
```

**Pros**: Modern, flexible  
**Cons**: Less common

**Recommendation**: Use `uv` for speed and simplicity.

---

## Migration Example

### Before (Single Package)
```python
# polytrader/risk/engine.py
from polytrader.events import EventBus
from polytrader.events.types import RiskCheckEvent
from polytrader.oms.models import Order
```

### After (Multi-Package)
```python
# packages/risk/src/polytrader_risk/engine.py
from polytrader_core.events import EventBus
from polytrader_core.events.types import RiskCheckEvent
from polytrader_oms.models import Order
```

### Package Dependencies (pyproject.toml)
```toml
# packages/risk/pyproject.toml
[project]
name = "polytrader-risk"
dependencies = [
    "polytrader-core",
    "polytrader-portfolio",
]
```

---

## Testing Strategy

### Unit Tests
- Each package has its own `tests/` directory
- Tests run in isolation
- Mock dependencies from other packages

### Integration Tests
- Live in root `tests/integration/`
- Test cross-package interactions
- Use installed packages (not source)

### CI/CD Changes
```yaml
# .github/workflows/test.yml
- name: Test packages
  run: |
    uv sync --all-packages
    uv run pytest packages/*/tests/
    uv run pytest tests/integration/
```

---

## Compatibility with Architecture Rules

This proposal **aligns with** existing architecture rules:

- **`architecture.mdc` §3**: "Phase 2: Split into services... keep SAME boundaries"
  - Packages = future service boundaries
- **`vision.mdc` §2**: "Institutional Repo Structure"
  - Multi-package structure matches recommended layout
- **`flows.mdc`**: Pipeline stages map 1:1 to packages
  - Clear separation of concerns

---

## Decision Criteria

**Proceed if:**
- ✅ System has clear architectural boundaries (✓ confirmed)
- ✅ Circular import issues exist (✓ confirmed)
- ✅ Team size > 2 people (verify)
- ✅ System will grow (verify)
- ✅ Migration effort is acceptable (8-10 days)

**Defer if:**
- ❌ System is very small (< 5 modules)
- ❌ Team is 1 person
- ❌ System is in maintenance mode only

---

## Next Steps

1. **Review this proposal** with team
2. **Choose workspace tooling** (recommend `uv`)
3. **Create ADR** documenting decision
4. **Start Phase 1** (workspace setup)
5. **Migrate incrementally** (one package per PR)

---

## References

- `.cursor/rules/architecture.mdc` — Module boundaries
- `.cursor/rules/vision.mdc` — Ideal repo structure
- `.cursor/rules/flows.mdc` — Pipeline stages
- [Dropbox: Atlas Journey](https://dropbox.tech/infrastructure/atlas--our-journey-from-a-python-monolith-to-a-managed-platform)
- [Opendoor: Python Monorepo](https://medium.com/opendoor-labs/our-python-monorepo-d34028f2b6fa)
