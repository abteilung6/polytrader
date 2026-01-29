# ValidateStrategyConfigRequest

Request to validate a strategy configuration.  Per Commit 16: ValidateStrategyConfigRequest allows clients to validate configurations before creating strategy instances.  Attributes:     template_type_id: Template type identifier (e.g., \'simple_threshold\')     version_selector: Version selector (exact version or channel)     config: Configuration dictionary to validate

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**template_type_id** | **string** | Template type identifier (e.g., \&#39;simple_threshold\&#39;) | [default to undefined]
**version_selector** | [**VersionSelectorRequest**](VersionSelectorRequest.md) | Version selector (exact version or channel) | [default to undefined]
**config** | **{ [key: string]: any; }** | Strategy configuration to validate | [default to undefined]

## Example

```typescript
import { ValidateStrategyConfigRequest } from '@polytrader/api-client';

const instance: ValidateStrategyConfigRequest = {
    template_type_id,
    version_selector,
    config,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
