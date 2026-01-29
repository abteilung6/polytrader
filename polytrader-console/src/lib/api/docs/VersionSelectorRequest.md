# VersionSelectorRequest

Version selector request model.  Per Commit 14: VersionSelectorRequest allows clients to specify either an exact version or a channel selector for strategy templates.  Attributes:     exact: Exact version string (e.g., \"1.2.3\") or None     channel: Channel name (\"stable\", \"beta\", \"dev\") or None     major: Major version number for channel selection (e.g., 1) or None

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**exact** | **string** |  | [optional] [default to undefined]
**channel** | **string** |  | [optional] [default to undefined]
**major** | **number** |  | [optional] [default to undefined]

## Example

```typescript
import { VersionSelectorRequest } from '@polytrader/api-client';

const instance: VersionSelectorRequest = {
    exact,
    channel,
    major,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
