# PerformanceOverviewItemResponse

One row per strategy instance — aggregated closed-trade performance.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**strategy_id** | **string** | Strategy instance identifier | [default to undefined]
**name** | **string** | Human-readable strategy name | [default to undefined]
**template_type_id** | **string** | Strategy template type | [default to undefined]
**template_version** | **string** | Strategy template version | [default to undefined]
**actual_state** | **string** | Current lifecycle state | [default to undefined]
**trade_count** | **number** | Number of closed trades in window | [default to undefined]
**wins** | **number** | Number of winning trades | [default to undefined]
**losses** | **number** | Number of losing trades | [default to undefined]
**breakevens** | **number** | Number of breakeven trades | [default to undefined]
**total_realized_pnl** | **number** | Sum of realized P&amp;L (USD) | [default to undefined]
**avg_trade_pnl** | **number** |  | [optional] [default to undefined]
**win_rate_pct** | **number** |  | [optional] [default to undefined]
**profit_factor** | **number** |  | [optional] [default to undefined]
**last_trade_exit_ts_wall** | **string** |  | [optional] [default to undefined]
**evidence_tier** | **string** | Evidence quality tier | [default to undefined]

## Example

```typescript
import { PerformanceOverviewItemResponse } from '@polytrader/api-client';

const instance: PerformanceOverviewItemResponse = {
    strategy_id,
    name,
    template_type_id,
    template_version,
    actual_state,
    trade_count,
    wins,
    losses,
    breakevens,
    total_realized_pnl,
    avg_trade_pnl,
    win_rate_pct,
    profit_factor,
    last_trade_exit_ts_wall,
    evidence_tier,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
