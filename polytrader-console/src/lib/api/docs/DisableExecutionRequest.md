# DisableExecutionRequest

Request to disable execution.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**expected_version** | **number** |  | [optional] [default to undefined]
**reason** | **string** | Reason for disabling execution | [default to undefined]
**issued_by** | **string** | User/system issuing the command | [default to undefined]
**client_request_id** | **string** | Client request ID for idempotency | [default to undefined]

## Example

```typescript
import { DisableExecutionRequest } from '@polytrader/api-client';

const instance: DisableExecutionRequest = {
    expected_version,
    reason,
    issued_by,
    client_request_id,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
