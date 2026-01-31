# StrategyOrdersResponse

Paginated list of orders for a strategy.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**items** | [**Array&lt;StrategyOrderItem&gt;**](StrategyOrderItem.md) | Order records (newest first) | [default to undefined]
**next_cursor** | **string** |  | [optional] [default to undefined]

## Example

```typescript
import { StrategyOrdersResponse } from '@polytrader/api-client';

const instance: StrategyOrdersResponse = {
    items,
    next_cursor,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
