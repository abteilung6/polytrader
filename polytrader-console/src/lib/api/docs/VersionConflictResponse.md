# VersionConflictResponse

Version conflict error response (409 Conflict).

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**error** | **string** |  | [optional] [default to 'Version conflict']
**expected_version** | **number** | Version that was expected | [default to undefined]
**actual_version** | **number** | Current version | [default to undefined]
**detail** | **string** | Explanation of the version conflict | [default to undefined]

## Example

```typescript
import { VersionConflictResponse } from '@polytrader/api-client';

const instance: VersionConflictResponse = {
    error,
    expected_version,
    actual_version,
    detail,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
