# ClosedTradeItem

Single closed trade for strategy performance API.  Per proposal-past-performance-tab: One row per StrategyClosedTradeEvent. entry_time/exit_time are monotonic timestamps; exit_ts_wall is wall-clock for display.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**market_slug** | **string** | Market identifier | [default to undefined]
**outcome** | **string** | Outcome traded | [default to undefined]
**entry_time** | **number** | Entry time (monotonic) | [default to undefined]
**exit_time** | **number** | Exit time (monotonic) | [default to undefined]
**exit_ts_wall** | **string** | Exit wall-clock time (UTC) | [default to undefined]
**entry_price** | **number** | Average entry price | [default to undefined]
**exit_price** | **number** | Exit fill/settlement price (0 allowed for binary settlement) | [default to undefined]
**size** | **number** | Position size in USD | [default to undefined]
**pnl** | **number** | Realized P&amp;L in USD | [default to undefined]
**pnl_pct** | **number** | Realized P&amp;L as percentage | [default to undefined]
**result** | **string** | WIN if pnl &gt; 0, LOSS if pnl &lt; 0, BREAKEVEN if pnl &#x3D;&#x3D; 0 | [default to undefined]
**execution_mode** | **string** | Paper or live execution | [default to undefined]
**duration_seconds** | **number** | Trade duration (exit_time - entry_time) in seconds | [default to undefined]

## Example

```typescript
import { ClosedTradeItem } from '@polytrader/api-client';

const instance: ClosedTradeItem = {
    market_slug,
    outcome,
    entry_time,
    exit_time,
    exit_ts_wall,
    entry_price,
    exit_price,
    size,
    pnl,
    pnl_pct,
    result,
    execution_mode,
    duration_seconds,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
