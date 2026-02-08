# KillSwitchRequest

Request to activate the kill switch (emergency stop).  Per flows.mdc §13: Kill switch provides immediate stop-trading policy. Activating the kill switch immediately disables execution and emits KillSwitchEvent. This is a direct-apply action, not queued.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**reason** | **string** | Reason for activating kill switch | [default to undefined]
**cancel_open_orders** | **boolean** | Whether to cancel open orders when kill switch is activated | [optional] [default to true]
**issued_by** | **string** | User/system activating the kill switch | [optional] [default to 'operator']

## Example

```typescript
import { KillSwitchRequest } from '@polytrader/api-client';

const instance: KillSwitchRequest = {
    reason,
    cancel_open_orders,
    issued_by,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
