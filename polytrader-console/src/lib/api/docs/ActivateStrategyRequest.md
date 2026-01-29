# ActivateStrategyRequest

Request to activate strategy for live trading.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**reason** | **string** | Reason for activation | [default to undefined]
**issued_by** | **string** | User/system issuing the command | [default to undefined]
**client_request_id** | **string** | Client request ID for idempotency | [default to undefined]

## Example

```typescript
import { ActivateStrategyRequest } from '@polytrader/api-client';

const instance: ActivateStrategyRequest = {
    reason,
    issued_by,
    client_request_id,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
