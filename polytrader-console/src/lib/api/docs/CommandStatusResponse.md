# CommandStatusResponse

Command status response.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**command_id** | **string** | Command identifier (UUID) | [default to undefined]
**type** | **string** | Command type | [default to undefined]
**status** | **string** | Command status | [default to undefined]
**error_message** | **string** |  | [optional] [default to undefined]
**created_at** | **string** | Command creation timestamp | [default to undefined]
**applied_at** | **string** |  | [optional] [default to undefined]
**reason** | **string** | Reason for the command | [default to undefined]
**issued_by** | **string** | User/system that issued the command | [default to undefined]

## Example

```typescript
import { CommandStatusResponse } from '@polytrader/api-client';

const instance: CommandStatusResponse = {
    command_id,
    type,
    status,
    error_message,
    created_at,
    applied_at,
    reason,
    issued_by,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
