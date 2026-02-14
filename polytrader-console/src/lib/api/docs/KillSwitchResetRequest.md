# KillSwitchResetRequest

Request to reset (deactivate) the kill switch.  Resetting the kill switch does NOT re-enable execution — the operator must explicitly re-enable execution separately. This is a safety measure to prevent accidental re-enablement.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**reason** | **string** | Reason for resetting kill switch | [default to undefined]
**issued_by** | **string** | User/system resetting the kill switch | [optional] [default to 'operator']

## Example

```typescript
import { KillSwitchResetRequest } from '@polytrader/api-client';

const instance: KillSwitchResetRequest = {
    reason,
    issued_by,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
