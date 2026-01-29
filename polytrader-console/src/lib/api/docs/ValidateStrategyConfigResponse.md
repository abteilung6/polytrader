# ValidateStrategyConfigResponse

Response from strategy configuration validation.  Per Commit 16: ValidateStrategyConfigResponse provides validation results with clear error messages and warnings.  Attributes:     valid: Whether the configuration is valid     errors: List of validation error messages (empty if valid)     warnings: List of validation warnings (optional issues)     template_type_id: Template type identifier used for validation     template_version: Resolved template version used for validation

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**valid** | **boolean** | Whether the configuration is valid | [default to undefined]
**errors** | **Array&lt;string&gt;** | List of validation error messages | [optional] [default to undefined]
**warnings** | **Array&lt;string&gt;** | List of validation warnings (optional issues) | [optional] [default to undefined]
**template_type_id** | **string** | Template type identifier used for validation | [default to undefined]
**template_version** | **string** | Resolved template version used for validation | [default to undefined]

## Example

```typescript
import { ValidateStrategyConfigResponse } from '@polytrader/api-client';

const instance: ValidateStrategyConfigResponse = {
    valid,
    errors,
    warnings,
    template_type_id,
    template_version,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
