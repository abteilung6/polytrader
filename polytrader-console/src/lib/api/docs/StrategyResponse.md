# StrategyResponse

Strategy registry entry response.  Per Commit 14: StrategyResponse includes all new fields for template reference, lifecycle state, and reproducibility metadata.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**strategy_id** | **string** | Strategy identifier | [default to undefined]
**name** | **string** | Human-readable strategy name | [default to undefined]
**description** | **string** |  | [optional] [default to undefined]
**config** | **{ [key: string]: any; }** | Strategy configuration (JSONB) | [default to undefined]
**template_type_id** | **string** | Template type identifier (e.g., \&#39;simple_threshold\&#39;) | [default to undefined]
**template_version** | **string** | Resolved template version (e.g., \&#39;1.0.0\&#39;) | [default to undefined]
**desired_state** | **string** | Desired lifecycle state (STOPPED | STARTING | RUNNING | etc.) | [default to undefined]
**actual_state** | **string** | Actual runtime state (STOPPED | STARTING | RUNNING | etc.) | [default to undefined]
**last_transition_at** | **string** |  | [optional] [default to undefined]
**last_error** | **string** |  | [optional] [default to undefined]
**run_identity** | [**RunIdentityResponse**](RunIdentityResponse.md) |  | [optional] [default to undefined]
**deployment_id** | **string** |  | [optional] [default to undefined]
**run_id** | **string** |  | [optional] [default to undefined]
**created_at** | **string** | Creation timestamp | [default to undefined]
**updated_at** | **string** | Last update timestamp | [default to undefined]
**enabled** | **boolean** | Whether strategy is enabled (derived from desired_state &#x3D;&#x3D; RUNNING). | [readonly] [default to undefined]

## Example

```typescript
import { StrategyResponse } from '@polytrader/api-client';

const instance: StrategyResponse = {
    strategy_id,
    name,
    description,
    config,
    template_type_id,
    template_version,
    desired_state,
    actual_state,
    last_transition_at,
    last_error,
    run_identity,
    deployment_id,
    run_id,
    created_at,
    updated_at,
    enabled,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
