# MarketsResponse

Markets list response.  Markets are ordered by latest_tick_ts descending (newest first). Markets with null latest_tick_ts appear last.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**markets** | [**Array&lt;MarketInfoResponse&gt;**](MarketInfoResponse.md) | List of markets (ordered newest first) | [default to undefined]
**count** | **number** | Number of markets | [default to undefined]

## Example

```typescript
import { MarketsResponse } from '@polytrader/api-client';

const instance: MarketsResponse = {
    markets,
    count,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
