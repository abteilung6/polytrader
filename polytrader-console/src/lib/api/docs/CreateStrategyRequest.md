# CreateStrategyRequest

Request to create a new strategy.  Per Commit 14: CreateStrategyRequest includes version_selector and desired_state instead of enabled boolean.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**strategy_id** | **string** | Strategy identifier | [default to undefined]
**name** | **string** | Human-readable strategy name | [default to undefined]
**description** | **string** |  | [optional] [default to undefined]
**config** | **{ [key: string]: any; }** | Strategy configuration (JSONB) | [default to undefined]
**template_type_id** | **string** | Template type identifier (e.g., \&#39;simple_threshold\&#39;) | [default to undefined]
**version_selector** | [**VersionSelectorRequest**](VersionSelectorRequest.md) | Version selector (exact version or channel) | [default to undefined]
**desired_state** | **string** | Desired lifecycle state (default: STOPPED) | [optional] [default to DesiredStateEnum_Stopped]

## Example

```typescript
import { CreateStrategyRequest } from '@polytrader/api-client';

const instance: CreateStrategyRequest = {
    strategy_id,
    name,
    description,
    config,
    template_type_id,
    version_selector,
    desired_state,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
