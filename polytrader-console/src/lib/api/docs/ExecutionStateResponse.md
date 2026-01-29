# ExecutionStateResponse

Execution control state response.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**execution_enabled** | **boolean** | Whether execution is enabled | [default to undefined]
**version** | **number** | Version for optimistic concurrency | [default to undefined]
**updated_at** | **string** | Last update timestamp | [default to undefined]
**updated_by** | **string** | User/system that made the update | [default to undefined]
**reason** | **string** | Reason for the update | [default to undefined]

## Example

```typescript
import { ExecutionStateResponse } from '@polytrader/api-client';

const instance: ExecutionStateResponse = {
    execution_enabled,
    version,
    updated_at,
    updated_by,
    reason,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
