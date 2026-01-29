# StrategyTypeResponse

Strategy template type response.  Per Commit 14: StrategyTypeResponse exposes strategy template information for discovery and selection.  Attributes:     type_id: Template type identifier (e.g., \'simple_threshold\')     name: Human-readable template name     description: Template description     available_versions: List of available versions     parameter_schema: OpenAPI-compatible parameter schema

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**type_id** | **string** | Template type identifier (e.g., \&#39;simple_threshold\&#39;) | [default to undefined]
**name** | **string** | Human-readable template name | [default to undefined]
**description** | **string** | Template description | [default to undefined]
**available_versions** | **Array&lt;string&gt;** | List of available versions | [default to undefined]
**parameter_schema** | **{ [key: string]: any; }** | OpenAPI-compatible parameter schema | [default to undefined]

## Example

```typescript
import { StrategyTypeResponse } from '@polytrader/api-client';

const instance: StrategyTypeResponse = {
    type_id,
    name,
    description,
    available_versions,
    parameter_schema,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
