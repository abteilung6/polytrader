# PerformanceResponse

Past performance for a strategy: summary + paginated closed trades.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**summary** | [**PerformanceSummary**](PerformanceSummary.md) | Aggregates over returned items | [default to undefined]
**items** | [**Array&lt;ClosedTradeItem&gt;**](ClosedTradeItem.md) | Closed trades (newest first) | [optional] [default to undefined]
**next_cursor** | **string** |  | [optional] [default to undefined]

## Example

```typescript
import { PerformanceResponse } from '@polytrader/api-client';

const instance: PerformanceResponse = {
    summary,
    items,
    next_cursor,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
