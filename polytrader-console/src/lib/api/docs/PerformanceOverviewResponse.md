# PerformanceOverviewResponse

Aggregated performance across all strategy instances.  Per proposal §7.3: Response includes resolved timestamps, evidence threshold, and per-strategy aggregates.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**from_ts_wall** | **string** |  | [default to undefined]
**to_ts_wall** | **string** | Resolved upper bound (UTC) | [default to undefined]
**execution_mode** | **string** |  | [optional] [default to undefined]
**min_trades_threshold** | **number** | Threshold used for evidence tier computation | [default to undefined]
**items** | [**Array&lt;PerformanceOverviewItemResponse&gt;**](PerformanceOverviewItemResponse.md) | Per-strategy performance aggregates | [default to undefined]

## Example

```typescript
import { PerformanceOverviewResponse } from '@polytrader/api-client';

const instance: PerformanceOverviewResponse = {
    from_ts_wall,
    to_ts_wall,
    execution_mode,
    min_trades_threshold,
    items,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
