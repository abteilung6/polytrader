# PerformanceSummary

Aggregate performance metrics for the returned closed trades.  Computed from the items in this response (page-scoped). When items are empty, total_trades=0, total_realized_pnl=0, win_rate_pct=None.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**total_realized_pnl** | **number** | Sum of P&amp;L over returned trades (USD) | [default to undefined]
**total_trades** | **number** | Number of trades in this page | [default to undefined]
**win_rate_pct** | **number** |  | [optional] [default to undefined]
**current_drawdown** | **number** |  | [optional] [default to undefined]
**max_drawdown** | **number** |  | [optional] [default to undefined]

## Example

```typescript
import { PerformanceSummary } from '@polytrader/api-client';

const instance: PerformanceSummary = {
    total_realized_pnl,
    total_trades,
    win_rate_pct,
    current_drawdown,
    max_drawdown,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
