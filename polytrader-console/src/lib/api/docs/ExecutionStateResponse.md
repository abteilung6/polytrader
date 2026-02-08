# ExecutionStateResponse

Execution control state response.  Includes both DB-persisted execution_enabled state and in-memory kill_switch_active state for the frontend control page.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**execution_enabled** | **boolean** | Whether execution is enabled | [default to undefined]
**kill_switch_active** | **boolean** | Whether kill switch is active (in-memory state) | [optional] [default to false]
**version** | **number** | Version for optimistic concurrency | [default to undefined]
**updated_at** | **string** | Last update timestamp | [default to undefined]
**updated_by** | **string** | User/system that made the update | [default to undefined]
**reason** | **string** | Reason for the update | [default to undefined]

## Example

```typescript
import { ExecutionStateResponse } from '@polytrader/api-client';

const instance: ExecutionStateResponse = {
    execution_enabled,
    kill_switch_active,
    version,
    updated_at,
    updated_by,
    reason,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
