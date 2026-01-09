# Model Architecture — Profit-Targeted Binary Outcome Strategy

This document specifies a directional, profit-targeted trading model for binary outcome markets (e.g., Polymarket UP/DOWN contracts with fixed $1 payout at settlement).

**Document Purpose:**  
This is a specification document that defines the model's logic, behavior, and requirements. Implementation details, code structure, and naming are left to the implementer. This serves as the source of truth for building a fresh implementation.

---

## 1. Executive Summary

### One-Line Mental Model

> "Wait for the market to imply a strong directional bias, then size a single directional position so that the portfolio earns a fixed profit if that outcome settles — fully accepting a capped but non-zero probability of total loss of the invested capital."

### Strategy Classification

| Dimension | Classification |
|-----------|---------------|
| **Alpha Source** | Market-implied probability (price threshold crossing) |
| **Trade Style** | Directional (bets on one outcome) |
| **Time Horizon** | Event-based (until settlement) |
| **Neutrality** | Non-neutral |
| **Risk Shape** | Asymmetric (fixed gain, variable loss) |
| **Capital Usage** | Discrete, step-function |
| **Turnover** | Low (1–N buys, no sells) |

**Strategic Category:** Event-driven directional trading  
**NOT:** Market making, statistical arbitrage, delta-neutral strategies

### Core Principle

This model targets **fixed upside** but exposes **variable downside**. The strategy does not hedge by design. Risk is directional and binary. Loss realization happens at settlement, not continuously.

---

## 2. Market Context

### Market Type
- **Binary outcome markets** (e.g., Polymarket BTC UP/DOWN)
- **Fixed payout:** $1 per share if chosen outcome settles
- **Settlement-based P&L:** No continuous mark-to-market
- **Two outcomes per market:** UP and DOWN (mutually exclusive)

### Required Market Inputs
- `up_price`: Best ask price for UP outcome (0.0 to 1.0)
- `down_price`: Best ask price for DOWN outcome (0.0 to 1.0)
- `market_id`: Unique market identifier
- (Optional) `timestamp`: For backtesting/replay

### Portfolio Inputs Required
- Cash balance (USDC)
- Existing positions per market/outcome:
  - Quantity (shares)
  - Average entry price
- Total invested capital per market

---

## 3. Model Parameters

All parameters must be validated and versioned per institutional standards.

| Parameter | Type | Default | Constraints | Purpose |
|-----------|------|---------|-------------|---------|
| `winner_threshold` | float | 0.60 | 0.0 ≤ x ≤ 1.0 | Minimum price to declare an outcome as likely winner |
| `max_buy_price` | float | 0.65 | 0.0 ≤ x ≤ 1.0 | Upper bound on acceptable entry price |
| `target_profit_usdc` | float | 10.0 | x > 0 | Desired profit if chosen outcome wins |
| `min_trade_amount_usdc` | float | 1.0 | x > 0 | Minimum order size (guard against dust) |
| `max_capital_per_market_usdc` | float | 500.0 | x > 0 | Hard risk cap per market (total invested) |

### Parameter Relationships

- `winner_threshold ≤ max_buy_price` (enforced)
- `target_profit_usdc` determines position sizing (see §5)
- `max_capital_per_market_usdc` is the primary risk control

### Parameter Impact on Behavior

- **Lower `winner_threshold`:** More aggressive entry, earlier signals
- **Higher `max_buy_price`:** Accepts more expensive entries, larger position sizes
- **Higher `target_profit_usdc`:** Larger positions, higher capital usage, higher max loss
- **Lower `max_capital_per_market_usdc`:** Stricter risk cap, may prevent reaching target profit

---

## 4. Decision Flow (Deterministic Algorithm)

The model's decision logic is **deterministic and stateless** (except for per-market declared winner state). Given the same inputs, it must produce the same output.

### Step 1: Guard Checks (Early Exit)

Abort evaluation if any of the following are true:

1. **Balance check:** `portfolio.balance < min_trade_amount_usdc`
2. **Price validity:** `up_price ≤ 0 OR down_price ≤ 0`
3. **Capital cap:** `total_invested_capital ≥ max_capital_per_market_usdc`

If any guard fails, return `None` (no order).

### Step 2: Outcome Validity Determination

For each outcome (UP, DOWN), determine if it is **valid**:

```
valid(price) = (price ≥ winner_threshold) AND (price ≤ max_buy_price)
```

- `up_valid = valid(up_price)`
- `down_valid = valid(down_price)`

### Step 3: Winner Declaration Logic

The model maintains per-market state: `declared_winner ∈ {"UP", "DOWN", None}`

**Reset conditions** (if current `declared_winner` is set):
- If declared winner's price > `max_buy_price` → reset to `None`
- If declared winner's price < `winner_threshold` → reset to `None`
- If declared winner becomes invalid for any reason → reset to `None`

**Declaration rules** (applied after reset checks):

1. **Single valid outcome:**
   - If `up_valid AND NOT down_valid` → declare "UP"
   - If `down_valid AND NOT up_valid` → declare "DOWN"

2. **Both outcomes valid:**
   - If `declared_winner` is already set and still valid → keep it
   - If `declared_winner` is `None` → select cheaper outcome (lower price)

3. **No valid outcomes:**
   - Keep `declared_winner` as `None` (or reset if previously set)

**Key invariant:** The model avoids oscillating between outcomes by maintaining `declared_winner` state until reset conditions are met.

### Step 4: Sizing Calculation

If `declared_winner` is set and valid, calculate required investment:

**Formula:**
```
existing_total_cost = sum(all positions: quantity × avg_price)
existing_shares = position quantity for declared_winner outcome (or 0 if none)
current_profit_if_winner = (existing_shares × 1.0) - existing_total_cost

IF current_profit_if_winner ≥ target_profit_usdc:
    return None  # Already reached target

needed_profit = target_profit_usdc - current_profit_if_winner
required_investment = needed_profit × price / (1.0 - price)
```

**Where:**
- `price` = current ask price of `declared_winner` outcome
- `needed_profit` = remaining profit needed to reach target
- `required_investment` = amount to spend (USDC) to achieve `needed_profit`

**Validation:**
- If `required_investment < min_trade_amount_usdc` → return `None`
- If `portfolio.balance < required_investment` → return `None`

### Step 5: Order Generation

If sizing calculation succeeds, emit a **single BUY order**:

- **Side:** BUY (always)
- **Outcome:** `declared_winner` ("UP" or "DOWN")
- **Size:** `required_investment` (USDC)
- **Limit Price:** Current ask price of `declared_winner` outcome
- **Reason:** Descriptive string including `target_profit_usdc`, `declared_winner`, rationale

**No SELL orders are generated.** The model only accumulates long positions.

---

## 5. Position Sizing Formula (Mathematical Specification)

### Core Formula

For outcome price `p` (0 < p < 1) and remaining required profit `P`:

```
required_investment = P × p / (1 - p)
```

### Derivation

Given:
- Binary outcome pays $1 per share if winner settles
- Current price `p` implies probability `p` of winning
- We need profit `P` if winner settles

If we buy `q` shares at price `p`:
- Cost = `q × p`
- Profit if winner = `q × 1 - q × p = q × (1 - p)`

To achieve profit `P`:
```
q × (1 - p) = P
q = P / (1 - p)
```

Investment required:
```
required_investment = q × p = P × p / (1 - p)
```

### Portfolio-Aware Calculation

The formula accounts for existing positions:

1. **Calculate existing total cost:**
   ```
   existing_total_cost = Σ(quantity_i × avg_price_i) for all positions in market
   ```

2. **Calculate existing shares for declared winner:**
   ```
   existing_shares = quantity of declared_winner outcome (or 0 if none)
   ```

3. **Calculate current profit if winner:**
   ```
   current_profit_if_winner = (existing_shares × 1.0) - existing_total_cost
   ```

4. **Calculate remaining profit needed:**
   ```
   needed_profit = max(0, target_profit_usdc - current_profit_if_winner)
   ```

5. **Apply formula:**
   ```
   required_investment = needed_profit × price / (1.0 - price)
   ```

### Loss Characteristics

**Worst-case loss** (if declared winner loses at settlement):
```
max_loss ≈ required_investment
```

**Example:** At prices 0.60–0.65 and `target_profit_usdc = 5`:
- Loss range ≈ 7.5–9.3 USDC

**Key property:** This strategy targets fixed upside but exposes variable downside.

### Partial Fill Handling

If an order is partially filled:
1. Portfolio state updates with partial fill
2. On next evaluation cycle, model recalculates:
   - `current_profit_if_winner` includes partial fill
   - `needed_profit` is reduced
   - New `required_investment` is calculated
3. Model emits new order for remaining amount (if needed)

This is **implicit partial fill handling** via portfolio re-evaluation.

---

## 6. State Requirements (Per Market)

### Required State

The model must maintain per-market state:

```python
declared_winner: "UP" | "DOWN" | None
```

### State Purpose

1. **Avoid oscillation:** Prevents rapid switching between UP and DOWN
2. **Track current bias:** Records which outcome is currently considered the winner
3. **Enable recalculation:** Allows sizing recalculation after partial fills

### State Transitions

**Declaration:**
- `None → "UP"` or `None → "DOWN"` when valid outcome is detected
- `"UP" → "DOWN"` or `"DOWN" → "UP"` only after reset

**Reset:**
- `"UP" → None` or `"DOWN" → None` when:
  - Price > `max_buy_price`
  - Price < `winner_threshold`
  - Outcome becomes invalid

### Derived State (Not Stored)

`buy_done: bool` is **derived** from portfolio state:
- `buy_done = True` if `current_profit_if_winner ≥ target_profit_usdc`
- `buy_done = False` otherwise

This is computed on each evaluation, not stored.

### State Persistence

**Phase 1 (Initial):** In-memory state (lost on restart)  
**Phase 2 (Target):** Event-sourced state (rebuildable from event log)

State transitions should emit events for auditability:
- `WinnerDeclaredEvent(market_id, outcome, price, threshold)`
- `WinnerResetEvent(market_id, previous_winner, reason)`

---

## 7. Risk Characteristics

### What the Model IS

- **Directional:** Bets on one outcome (not hedged)
- **Profit-targeted:** Fixed upside (`target_profit_usdc`)
- **Price-confirmation based:** Uses market-implied probability (price threshold)
- **Partial-fill resilient:** Recalculates after each fill
- **Settlement-based:** Holds until settlement (no pre-settlement exit)

### What the Model IS NOT

- **NOT hedged:** Does not offset risk with opposite positions
- **NOT market neutral:** Has directional exposure
- **NOT arbitrage:** Does not guarantee profit
- **NOT fee-aware:** Fees and slippage not included in sizing
- **NOT exit-capable:** No pre-settlement exit logic

### Risk Exposure per Market

- **Risk is directional and binary**
- **Loss realization happens at settlement**, not continuously
- **Max loss ≈ invested capital** (if declared winner loses)

### Loss Scenarios

**Single-outcome trade (no switch):**
- Max loss ≈ `required_investment`
- At prices 0.60–0.65 and `target_profit_usdc = 5`:
  - Max loss ≈ 7.5–9.3 USDC

**Outcome switch enabled:**
- Model may accumulate positions on both sides
- This is **NOT hedging**; it is sequential directional exposure
- Loss magnitude increases as prior losses are incorporated into new profit targets
- Absolute loss bounded only by `max_capital_per_market_usdc`

**Key Property:**
```
This strategy targets fixed upside but exposes variable downside.
```

---

## 8. Edge Cases & Failure Modes

### 8.1 Outcome Switching

**Description:** If `declared_winner` resets and the opposite side becomes valid, the model may accumulate positions on both sides.

**When it occurs:**
- Declared winner becomes invalid (price too high or below threshold)
- Opposite side becomes valid
- Model declares new winner and sizes new position

**Impact:**
- Not hedging; sequential directional exposure
- Capital amplification (prior losses included in profit targeting)
- Risk bounded only by `max_capital_per_market_usdc`

**Observability:** Emit `OutcomeSwitchEvent` when switch occurs.

### 8.2 Capital Amplification

**Description:** Switching increases required capital because prior losses are included in profit targeting.

**Example:**
- First trade: Invest 10 USDC, lose 10 USDC
- Second trade (switch): Need to make 10 USDC profit + recover 10 USDC loss = 20 USDC total
- Required investment increases proportionally

**Impact:** Capital usage grows with each switch.

**Mitigation:** `max_capital_per_market_usdc` hard cap.

### 8.3 Partial Fill Incomplete

**Description:** Target profit not reached after partial fill.

**When it occurs:**
- Order partially filled
- Portfolio updated with partial fill
- Next evaluation recalculates remaining amount needed

**Impact:** Model emits new order for remaining amount (handled implicitly).

**Observability:** Track partial fills and recalculations.

### 8.4 Capital Exhaustion

**Description:** Reached `max_capital_per_market_usdc` before target profit reached.

**When it occurs:**
- Multiple partial fills or switches
- Total invested capital reaches cap
- Guard check prevents further orders

**Impact:** Model cannot reach target profit for this market.

**Observability:** Emit `CapitalExhaustionEvent` when cap reached.

### 8.5 Threshold Oscillation ("Winner Flapping")

**Description:** Price oscillates around `winner_threshold`, causing repeated declaration/reset cycles.

**When it occurs:**
- Price hovers near `winner_threshold`
- Model declares winner, then resets, then declares again

**Impact:** Unnecessary order generation, potential capital waste.

**Mitigation:** Hysteresis (declare at 0.60, reset at 0.57) — future enhancement.

**Observability:** Track declaration/reset frequency.

### 8.6 No Fee Awareness

**Description:** Fees and slippage not included in sizing calculation.

**Impact:**
- Realized profit < `target_profit_usdc`
- Formula assumes perfect execution at best ask

**Mitigation:** Include fees in sizing formula — future enhancement.

---

## 9. Assumptions & Limitations

### Implicit Assumptions

The model assumes:

1. **Market prices above threshold imply positive expected value**
   - Violation: If threshold is too low, model may enter losing trades

2. **Probability does not revert strongly after crossing threshold**
   - Violation: If price reverts immediately, model may enter at peak

3. **Liquidity exists at or near best ask**
   - Violation: Slippage may reduce realized profit

4. **Fees are small relative to target profit**
   - Violation: Fees may dominate small target profits

5. **Settlement is the primary exit mechanism**
   - Violation: No pre-settlement exit means holding through adverse moves

**Critical:** Violating any of these assumptions materially degrades performance.

### Limitations

- **No hedging:** Full directional exposure
- **No exit logic:** Holds until settlement
- **No fee awareness:** Sizing ignores fees
- **No max-loss per trade:** Only bounded by `max_capital_per_market_usdc`
- **No hysteresis:** Threshold oscillation possible

These are **intentional simplifications**, not omissions.

---

## 10. Future Enhancements (Not in Initial Specification)

### A. Risk Controls

- **Enforce single-outcome-per-market (no switches):**
  - Add policy: if `declared_winner` is set, do not switch to opposite side
  - Prevents capital amplification from switching

- **Add hysteresis:**
  - Declare winner at `winner_threshold` (e.g., 0.60)
  - Reset winner at lower threshold (e.g., 0.57)
  - Prevents threshold oscillation

- **Explicit max-loss per trade:**
  - Add `max_loss_per_trade_usdc` parameter
  - Override sizing if `required_investment > max_loss_per_trade_usdc`
  - Independent of `target_profit_usdc`

### B. Fees & Slippage

- **Include fees in sizing formula:**
  - Adjust formula: `required_investment = (P + fees) × p / (1 - p)`
  - Account for expected slippage

- **Target net profit:**
  - Change from gross profit to net profit (after fees)
  - More realistic profit targeting

### C. Exit Logic

- **Optional pre-settlement exit:**
  - Exit if price moves favorably (take profit early)
  - Exit if price moves unfavorably (cut loss)

- **Time-based stop:**
  - Exit if position held for X days without settlement

- **Invalidation-based unwind:**
  - Exit if `declared_winner` becomes invalid
  - Realize loss early instead of holding to settlement

### D. State Management

- **Externalize per-market state:**
  - Store `declared_winner` in persistent store
  - Restart-safe state management

- **Event-sourced state transitions:**
  - Emit events for all state changes
  - Rebuildable from event log
  - Full audit trail

---

## 11. Observability Requirements

### Required Events

The model should emit events for:

1. **Winner Declaration:**
   - `WinnerDeclaredEvent(market_id, outcome, price, threshold)`
   - Emitted when `declared_winner` transitions from `None` to "UP" or "DOWN"

2. **Winner Reset:**
   - `WinnerResetEvent(market_id, previous_winner, reason)`
   - Emitted when `declared_winner` resets to `None`
   - Reason: "price_too_high" | "below_threshold" | "invalid"

3. **Outcome Switch:**
   - `OutcomeSwitchEvent(market_id, from_outcome, to_outcome, reason)`
   - Emitted when `declared_winner` switches from one outcome to another

4. **Capital Exhaustion:**
   - `CapitalExhaustionEvent(market_id, total_invested, cap)`
   - Emitted when `max_capital_per_market_usdc` reached

5. **Sizing Calculation:**
   - Log inputs: `current_profit_if_winner`, `needed_profit`, `price`
   - Log output: `required_investment`
   - Include in order intent metadata

### Required Metrics

- **Per market:**
  - `declared_winner` (gauge: "UP" | "DOWN" | "None")
  - `total_invested_capital` (gauge, USDC)
  - `current_profit_if_winner` (gauge, USDC)
  - `outcome_switches_total` (counter)

- **Global:**
  - `winner_declarations_total` (counter)
  - `winner_resets_total` (counter, by reason)
  - `capital_exhaustion_total` (counter)

### Required Logs

All logs must include:
- `market_id`
- `declared_winner` (if set)
- `correlation_id` (for order lifecycle tracing)
- `target_profit_usdc`
- `required_investment` (if order generated)

---

## 12. Testing Requirements

### Unit Tests

**Pure functions (deterministic, no side effects):**

1. **Sizing formula:**
   - Test with various prices (0.50, 0.60, 0.65, 0.70)
   - Test with existing positions (UP only, DOWN only, both)
   - Test edge cases (price = 0.99, price = 0.01)
   - Verify formula: `required_investment = P × p / (1 - p)`

2. **Winner declaration logic:**
   - Test single valid outcome
   - Test both valid (select cheaper)
   - Test reset conditions
   - Test state transitions

3. **Validity determination:**
   - Test `valid(price)` with boundary conditions
   - Test `winner_threshold` and `max_buy_price` boundaries

### Integration Tests

**Full decision flow with mock data:**

1. **Happy path:**
   - Valid market data → declare winner → calculate size → emit order
   - Verify order attributes (side, size, price, outcome)

2. **Partial fill handling:**
   - Emit order → simulate partial fill → verify recalculation
   - Verify new order for remaining amount

3. **Outcome switching:**
   - Declare UP → reset → declare DOWN
   - Verify both positions accumulate
   - Verify capital amplification

4. **Capital exhaustion:**
   - Multiple orders → reach cap → verify guard prevents further orders

### Property-Based Tests

**Invariants to verify:**

1. **Sizing formula invariant:**
   - For any valid `price` and `needed_profit`, `required_investment > 0`
   - `required_investment` increases as `price` increases (for fixed `needed_profit`)
   - `required_investment` increases as `needed_profit` increases (for fixed `price`)

2. **State transition invariant:**
   - `declared_winner` can only transition via valid paths
   - Reset conditions are mutually exclusive

3. **Capital usage invariant:**
   - `total_invested_capital ≤ max_capital_per_market_usdc` (always)

### Edge Case Tests

1. **Threshold oscillation:**
   - Price oscillates around `winner_threshold`
   - Verify behavior (may flap, or use hysteresis if implemented)

2. **Both outcomes at same price:**
   - `up_price = down_price = 0.60`
   - Verify selection logic (arbitrary but deterministic)

3. **Price = 0.99 (very expensive):**
   - Verify sizing calculation handles correctly
   - Verify `required_investment` is large

4. **Price = 0.01 (very cheap):**
   - Verify sizing calculation handles correctly
   - Verify `required_investment` is small

---

## 13. Implementation Notes

### Design Intent

This model serves as:
- A **foundation strategy**, not a final production system
- A clean baseline for adding:
  - Hedging
  - Exits
  - Smarter alpha
  - Institutional-grade risk controls

### Separation of Concerns

The model should separate:
- **Signal/Alpha:** Winner declaration (threshold crossing)
- **Portfolio Construction:** Sizing (profit-target calculation)
- **State Management:** Per-market `declared_winner` tracking
- **Risk:** Capital caps (enforced externally)

### Determinism

The model must be **deterministic**:
- Same inputs → same output
- No hidden state (except `declared_winner`)
- No randomness
- No network calls
- No time-dependent logic (except optional timestamp for backtesting)

### Testability

All logic should be:
- **Pure functions** where possible
- **Injectable dependencies** (portfolio state, market data)
- **Mockable** for unit tests
- **Replayable** from event log

---

## 14. Summary

This model implements a **directional, event-driven strategy** that:
1. Declares a winner when market-implied probability crosses a threshold
2. Sizes positions to achieve a fixed profit if the winner settles
3. Does not hedge, does not sell, accepts full loss when wrong
4. Is portfolio-aware, partial-fill resilient, and deterministic

**Risk is bounded by explicit capital caps, but the strategy targets fixed upside while exposing variable downside.**

This specification is implementation-agnostic and serves as the source of truth for building a fresh implementation that integrates with the institutional trading stack.

