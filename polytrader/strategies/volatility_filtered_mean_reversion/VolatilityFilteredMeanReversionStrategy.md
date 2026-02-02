# Volatility-Filtered Mean Reversion (VFMR)

This document describes the strategy from the algorithmic, mathematical, and probabilistic perspective.

---

## 1. Idea

Mean reversion assumes price temporarily deviates from a fair value and tends to revert. The strategy:

- **Quantifies deviation in volatility units.** Let \(z = (p - \mu) / \sigma\) where \(p\) is current price, \(\mu\) a fair-value anchor, \(\sigma\) a volatility scale (e.g. ATR). Large \(|z|\) means a large move relative to typical noise; entry triggers when \(|z| \geq \text{entry\_z}\).
- **Restricts to low-trend regimes.** In a strong short-term trend, reversion may be delayed or absent. A trend-strength measure (EMA gap normalized by volatility) is used as a regime gate: trade only when trend strength is below a threshold.
- **Outputs a probabilistic view.** On entry, the strategy emits a binary outcome (UP or DOWN) plus probabilities, edge, and confidence for downstream sizing and risk.

---

## 2. Quantities and Formulas

### 2.1 Input series

From tick data, **15-minute OHLC candles** are built. For each candle we have open \(O\), high \(H\), low \(L\), close \(C\). All following series are indexed by candle \(t\).

### 2.2 Volatility scale (ATR)

Average True Range over window \(n_{\text{atr}}\):

\[
\text{TR}_t = \max(H_t - L_t,\; |H_t - C_{t-1}|,\; |L_t - C_{t-1}|), \qquad
\text{ATR}_t = \text{EMA}(\text{TR}; n_{\text{atr}}).
\]

\(\text{ATR}_t\) is the volatility scale at \(t\). If \(\text{ATR}_t \leq 0\), no signal.

### 2.3 Fair-value anchor

Rolling mean of close over the last \(n_{\text{anchor}}\) candles:

\[
\mu_t = \frac{1}{n_{\text{anchor}}} \sum_{s = t - n_{\text{anchor}} + 1}^{t} C_s.
\]

So \(\mu_t\) is the fair-value anchor at \(t\).

### 2.4 Deviation (z-score in volatility units)

\[
z_t = \frac{C_t - \mu_t}{\text{ATR}_t}.
\]

So \(z_t\) is “how many ATRs” the close is above or below the anchor. Entry rules: \(z_t \geq \text{entry\_z} \Rightarrow\) bet DOWN (expect reversion down); \(z_t \leq -\text{entry\_z} \Rightarrow\) bet UP (expect reversion up).

### 2.5 Trend strength (regime gate)

Let \(\text{EMA}_{\text{fast}}\) and \(\text{EMA}_{\text{slow}}\) be EMAs of the close with periods \(n_{\text{fast}} < n_{\text{slow}}\). Define

\[
\text{trend\_strength}_t = \frac{|\text{EMA}_{\text{fast},t} - \text{EMA}_{\text{slow},t}|}{\text{ATR}_t}.
\]

Low values mean the short-term average is close to the longer-term one (sideways / mean-reversion regime). High values mean a strong short-term trend. Trading is allowed only when \(\text{trend\_strength}_t \leq \text{trend\_threshold}\).

---

## 3. Decision Rules

1. **Warmup:** No signal until at least \(\max(n_{\text{anchor}}, n_{\text{atr}}, n_{\text{slow}})\) candles are available.
2. **Regime gate:** If \(\text{trend\_strength}_t > \text{trend\_threshold}\), no signal.
3. **Exit logic:** If already in a position and \(|z_t| \leq \text{exit\_z}\) (reversion toward anchor), do not emit a new entry signal; exit is handled elsewhere. Require \(\text{exit\_z} < \text{entry\_z}\).
4. **Throttle:** At most \(\text{max\_trades\_per\_hour}\) signals per hour (wall-clock).
5. **One signal per candle:** At most one signal per candle close (e.g. keyed by candle start time).
6. **Entry (flat only):** If position is flat, regime OK, and \(|z_t| \geq \text{entry\_z}\):
   - If \(z_t \geq \text{entry\_z}\): outcome DOWN, bias probability toward DOWN (e.g. \(p_{\text{down}} > p_{\text{up}}\)).
   - If \(z_t \leq -\text{entry\_z}\): outcome UP, bias probability toward UP.
   - Edge can be set from \(|z_t| - \text{exit\_z}\); confidence from how far \(|z_t|\) is beyond the entry threshold (capped at 1).

---

## 4. Invariants (Constraints)

- \(n_{\text{slow}} > n_{\text{fast}}\) (slow EMA period strictly greater than fast).
- \(\text{exit\_z} < \text{entry\_z}\) (exit threshold strictly below entry so there is a reversion band).

---

## 5. Parameters

All parameters are numeric; bounds and defaults are defined in the schema and validated at creation.

| Parameter | Type | Default | Bounds | Role |
|-----------|------|--------|--------|------|
| `anchor_window` | int | 96 | 24–500 | \(n_{\text{anchor}}\): rolling window for \(\mu_t\) (~24h for 96×15m). |
| `atr_window` | int | 14 | 5–100 | \(n_{\text{atr}}\): ATR period. |
| `ema_fast` | int | 20 | 5–200 | \(n_{\text{fast}}\): fast EMA for trend. |
| `ema_slow` | int | 80 | 6–500 | \(n_{\text{slow}}\): slow EMA; must be > ema_fast. |
| `trend_threshold` | float | 0.5 | 0.01–5.0 | Max trend_strength to allow trading (regime gate). |
| `entry_z` | float | 1.5 | 0.5–5.0 | \(|z_t| \geq \text{entry\_z}\) to trigger entry. |
| `exit_z` | float | 0.3 | 0.0–2.0 | \(|z_t| \leq \text{exit\_z}\) to consider exit; must be < entry_z. |
| `risk_per_trade_pct` | float | 0.25 | 0.05–1.0 | Risk per trade (used downstream for sizing). |
| `max_position_notional_pct` | float | 100.0 | 1.0–100.0 | Cap position size (downstream). |
| `max_trades_per_hour` | int | 4 | 1–60 | Throttle: max signals per hour. |
| `cooldown_candles_after_loss` | int | 1 | 0–100 | Reserved (post-loss cooldown; behavior deferred). |

---

## 6. Parameter Space (Tuning)

- **Stricter regime / higher conviction:** Larger \(\text{entry\_z}\) (e.g. 1.8–2.0), smaller \(\text{trend\_threshold}\) (e.g. 0.35) → fewer signals, only when deviation is large and trend is weak.
- **Looser regime / more signals:** Smaller \(\text{entry\_z}\) (e.g. 1.0–1.2), larger \(\text{trend\_threshold}\) (e.g. 0.65–0.7) → more signals; allow slightly trending regimes.
- **Faster fair value:** Smaller \(\text{anchor\_window}\) (e.g. 48) → \(\mu_t\) reacts sooner to recent price.
- **Trend filter speed:** Larger gap \(n_{\text{slow}} - n_{\text{fast}}\) (e.g. 15/60) gives a slower trend measure; smaller gap (e.g. 10/40) gives a faster one.
- **Earlier exit signal:** Smaller \(\text{exit\_z}\) (e.g. 0.2) so the “reverted” condition is reached sooner.

For fixed-interval (e.g. 15-minute) expiry markets, one decision per candle aligns with resolution; warmup requires at least \(n_{\text{anchor}}\) candles. Running multiple instances with different parameter vectors spans the space of (entry threshold, regime threshold, anchor length, trend speed) and diversifies when and how often the strategy trades.
