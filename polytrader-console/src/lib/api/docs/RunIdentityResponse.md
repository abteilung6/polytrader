# RunIdentityResponse

Reproducibility metadata response.  Per Commit 14: RunIdentityResponse exposes reproducibility metadata for strategy instances, enabling deterministic replay.  Attributes:     template_code_ref: Git SHA / build artifact digest of template code     config_hash: SHA256 hash of config (for reproducibility)     dependency_set: Versions of key libs / model artifacts     market_data_snapshot_ref: Market data stream ID / snapshot reference

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**template_code_ref** | **string** |  | [optional] [default to undefined]
**config_hash** | **string** | SHA256 hash of config (for reproducibility) | [default to undefined]
**dependency_set** | **{ [key: string]: string; }** |  | [optional] [default to undefined]
**market_data_snapshot_ref** | **string** |  | [optional] [default to undefined]

## Example

```typescript
import { RunIdentityResponse } from '@polytrader/api-client';

const instance: RunIdentityResponse = {
    template_code_ref,
    config_hash,
    dependency_set,
    market_data_snapshot_ref,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
