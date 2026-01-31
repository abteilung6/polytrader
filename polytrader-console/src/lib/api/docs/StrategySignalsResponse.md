# StrategySignalsResponse

Paginated list of signals for a strategy.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**items** | [**Array&lt;StrategySignalItem&gt;**](StrategySignalItem.md) | Signal records (newest first) | [default to undefined]
**next_cursor** | **string** |  | [optional] [default to undefined]

## Example

```typescript
import { StrategySignalsResponse } from '@polytrader/api-client';

const instance: StrategySignalsResponse = {
    items,
    next_cursor,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
