# Test Speed Improvement Proposal

**Current State:**
- 782 tests across 67 test files
- Sequential execution (`pytest tests/ -v`)
- ~535 async tests (68% of suite)
- 296 fixtures across 26 files
- Mix of unit tests and integration tests
- No parallelization
- No test categorization/markers

**Target:** Reduce test execution time by 3-5x (from current baseline)

---

## Strategy 1: Parallel Execution with pytest-xdist (Highest Impact)

### Implementation
1. **Add pytest-xdist to requirements.dev.txt**
   ```
   pytest-xdist>=3.5.0
   ```

2. **Update Makefile**
   ```makefile
   test:
       pytest tests/ -v -n auto
   
   test-fast:
       pytest tests/ -v -n auto --ignore=tests/integration/
   
   test-integration:
       pytest tests/integration/ -v -n auto
   ```

3. **Configure in pyproject.toml**
   ```toml
   [tool.pytest.ini_options]
   asyncio_mode = "auto"
   pythonpath = ["."]
   # Parallel execution settings
   addopts = "-n auto --dist worksteal"
   ```

### Expected Impact
- **3-4x speedup** on multi-core systems (assuming 4-8 cores)
- Work-stealing scheduler balances load across workers
- `-n auto` uses CPU count automatically

### Considerations
- Some tests may need `@pytest.mark.no_parallel` if they share global state
- Integration tests with shared resources may need isolation
- Fixture scope becomes important (session vs function)

---

## Strategy 2: Test Categorization & Selective Execution

### Implementation
1. **Add test markers** to categorize tests:
   - `@pytest.mark.unit` - Fast, isolated unit tests
   - `@pytest.mark.integration` - Slower integration tests
   - `@pytest.mark.slow` - Tests that take >100ms
   - `@pytest.mark.asyncio` - Already present, but can be used for filtering

2. **Update pyproject.toml** with marker definitions:
   ```toml
   [tool.pytest.ini_options]
   markers = [
       "unit: Fast unit tests (default)",
       "integration: Integration tests with multiple components",
       "slow: Tests that take significant time (>100ms)",
   ]
   ```

3. **Create Makefile targets**:
   ```makefile
   test-unit:
       pytest tests/ -v -m "unit" -n auto
   
   test-integration:
       pytest tests/ -v -m "integration" -n auto
   
   test-fast:
       pytest tests/ -v -m "not slow" -n auto
   ```

### Expected Impact
- **2-3x speedup** for common development workflow (run unit tests only)
- CI can run full suite, developers run fast subset
- Faster feedback loop during development

### Migration Path
- Start by marking integration tests (already in `tests/integration/`)
- Identify slow tests using `pytest --durations=10`
- Gradually add markers as tests are touched

---

## Strategy 3: Optimize Fixture Scope & Caching

### Current State
- 296 fixtures across 26 files
- Many fixtures likely use `function` scope (recreated per test)

### Optimization Strategies

1. **Audit fixture scopes:**
   - Pure, stateless fixtures → `function` scope (OK)
   - Expensive setup (EventBus, stores) → `class` or `module` scope
   - Very expensive (system boot) → `session` scope

2. **Use `pytest.fixture(scope="class")` for test classes:**
   ```python
   @pytest.fixture(scope="class")
   def event_bus():
       return EventBus()  # Shared across all tests in class
   ```

3. **Consider `pytest.fixture(autouse=True)` for common setup:**
   - Only if truly needed by all tests in module
   - Reduces boilerplate but can hide dependencies

4. **Use `pytest.fixture(scope="session")` for immutable test data:**
   - Default limits, configs, static market data

### Expected Impact
- **1.5-2x speedup** for tests with expensive fixtures
- Reduces redundant setup/teardown
- Especially beneficial for integration tests

### Migration Path
- Profile fixture creation time: `pytest --setup-show`
- Identify expensive fixtures (>10ms setup)
- Gradually increase scope where safe

---

## Strategy 4: Test Selection & Filtering

### Implementation
1. **Use pytest's built-in filtering:**
   ```makefile
   test-changed:
       pytest tests/ -v --lf  # Last failed
   
   test-new:
       pytest tests/ -v --ff  # Failed first
   
   test-file:
       pytest tests/test_oms_core.py -v  # Specific file
   ```

2. **Add pytest-cache for test selection:**
   - Already included with pytest
   - `--lf` runs last-failed tests first
   - `--ff` runs failed tests first, then rest

3. **Use pytest-k (pytest-keep) for interactive selection:**
   ```bash
   pip install pytest-keep
   pytest -k "test_oms"  # Run tests matching pattern
   ```

### Expected Impact
- **10-50x speedup** for focused development (single file/module)
- Faster iteration during debugging
- CI still runs full suite

---

## Strategy 5: Async Test Optimization

### Current State
- ~535 async tests (68% of suite)
- Using `pytest-asyncio` with `asyncio_mode = "auto"`

### Optimization Strategies

1. **Use `pytest-asyncio` event loop policy:**
   ```toml
   [tool.pytest.ini_options]
   asyncio_mode = "auto"
   asyncio_default_fixture_loop_scope = "function"  # or "class"
   ```

2. **Consider `pytest-asyncio` parallel mode:**
   - Some async tests can run concurrently within same worker
   - Requires careful design to avoid shared state

3. **Use `asyncio.gather()` in tests that can parallelize:**
   - Instead of sequential `await`, batch operations

### Expected Impact
- **1.2-1.5x speedup** for async-heavy test suites
- Better resource utilization
- Less waiting on I/O-bound operations

---

## Strategy 6: CI/CD Optimization

### Implementation
1. **Split test runs in CI:**
   ```yaml
   # Example GitHub Actions
   test-unit:
     runs-on: ubuntu-latest
     steps:
       - run: make test-unit
   
   test-integration:
     runs-on: ubuntu-latest
     steps:
       - run: make test-integration
   ```

2. **Use test result caching:**
   - Cache pytest cache between runs
   - Only re-run changed tests when possible

3. **Parallelize CI jobs:**
   - Run unit and integration tests in parallel
   - Use matrix strategy for different Python versions

### Expected Impact
- **2-3x speedup** in CI pipeline
- Faster feedback on PRs
- Better resource utilization

---

## Recommended Implementation Order

### Phase 1: Quick Wins (1-2 hours)
1. ✅ Add `pytest-xdist` and enable `-n auto`
2. ✅ Add basic test markers (`unit`, `integration`)
3. ✅ Create `test-fast` target for unit tests only

**Expected: 2-3x speedup immediately**

### Phase 2: Optimization (2-4 hours)
4. ✅ Profile slow tests: `pytest --durations=10`
5. ✅ Optimize fixture scopes (class/module where safe)
6. ✅ Mark slow tests with `@pytest.mark.slow`

**Expected: Additional 1.5-2x speedup**

### Phase 3: Advanced (4-8 hours)
7. ✅ Refactor expensive fixtures to session scope
8. ✅ Add CI job splitting
9. ✅ Document test selection patterns

**Expected: Additional 1.2-1.5x speedup**

---

## Combined Expected Results

| Scenario | Current | After Phase 1 | After Phase 2 | After Phase 3 |
|----------|---------|---------------|---------------|---------------|
| Full suite (8 cores) | 100% | 25-33% | 15-20% | 10-15% |
| Unit tests only | 100% | 25-33% | 15-20% | 10-15% |
| Single file | 100% | 100% | 100% | 100% |
| CI pipeline | 100% | 50% | 30-40% | 20-30% |

**Total potential speedup: 5-10x for full suite, 10-20x for unit tests**

---

## Risks & Mitigations

### Risk 1: Test Isolation Issues
- **Problem:** Parallel execution may expose shared state bugs
- **Mitigation:** 
  - Start with `-n 2` (2 workers) to surface issues
  - Use `@pytest.mark.no_parallel` for problematic tests
  - Audit fixtures for global state

### Risk 2: Fixture Scope Changes Break Tests
- **Problem:** Changing fixture scope can cause test pollution
- **Mitigation:**
  - Change scope incrementally
  - Run full suite after each change
  - Use `pytest --setup-show` to verify isolation

### Risk 3: CI Complexity
- **Problem:** Multiple test jobs increase CI complexity
- **Mitigation:**
  - Start with single parallel job
  - Split only if needed for faster feedback
  - Use test result aggregation

---

## Measurement & Validation

### Before/After Metrics
1. **Baseline measurement:**
   ```bash
   time pytest tests/ -v  # Current time
   ```

2. **After each phase:**
   ```bash
   time pytest tests/ -v -n auto  # Phase 1
   time pytest tests/ -v -n auto -m "unit"  # Phase 2
   ```

3. **Track in CI:**
   - Add test duration to CI output
   - Monitor for regressions

### Success Criteria
- ✅ Full suite runs in <30% of original time
- ✅ Unit tests run in <20% of original time
- ✅ No test failures introduced
- ✅ CI pipeline time reduced by 50%+

---

## Alternative: pytest-parallel (if xdist has issues)

If `pytest-xdist` causes problems with async tests or fixtures:

```bash
pip install pytest-parallel
pytest tests/ --workers auto
```

**Trade-offs:**
- Better async support
- Simpler model (threads vs processes)
- May have different isolation characteristics

---

## Next Steps

1. **Measure baseline:** Run `time make test` and record duration
2. **Start Phase 1:** Add pytest-xdist, enable parallel execution
3. **Validate:** Ensure all tests pass with `-n auto`
4. **Measure improvement:** Compare new duration to baseline
5. **Iterate:** Proceed to Phase 2 if Phase 1 successful

---

## References

- [pytest-xdist documentation](https://pytest-xdist.readthedocs.io/)
- [pytest markers](https://docs.pytest.org/en/stable/how-to/mark.html)
- [pytest fixture scopes](https://docs.pytest.org/en/stable/how-to/fixtures.html#scope-sharing-fixtures-across-classes-modules-packages-or-session)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
