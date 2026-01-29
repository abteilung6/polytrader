# HealthResponse

System health response with gates.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**overall** | **string** | Overall status (worst gate status) | [default to undefined]
**gates** | [**HealthGates**](HealthGates.md) | Individual gate statuses | [default to undefined]

## Example

```typescript
import { HealthResponse } from '@polytrader/api-client';

const instance: HealthResponse = {
    overall,
    gates,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
