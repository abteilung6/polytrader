# UpdateStrategyRequest

Request to update an existing strategy.  Per Commit 14: UpdateStrategyRequest includes desired_state instead of enabled boolean.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**name** | **string** |  | [optional] [default to undefined]
**description** | **string** |  | [optional] [default to undefined]
**config** | **{ [key: string]: any; }** |  | [optional] [default to undefined]
**desired_state** | **string** |  | [optional] [default to undefined]

## Example

```typescript
import { UpdateStrategyRequest } from '@polytrader/api-client';

const instance: UpdateStrategyRequest = {
    name,
    description,
    config,
    desired_state,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
