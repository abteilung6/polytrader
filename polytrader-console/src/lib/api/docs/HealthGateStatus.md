# HealthGateStatus

Individual health gate status.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**status** | **string** | Gate status: ok, degraded, or down | [default to undefined]
**message** | **string** |  | [optional] [default to undefined]

## Example

```typescript
import { HealthGateStatus } from '@polytrader/api-client';

const instance: HealthGateStatus = {
    status,
    message,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
