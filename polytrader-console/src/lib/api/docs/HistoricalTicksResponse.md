# HistoricalTicksResponse

Historical ticks response.  For a 15-minute market window, all ticks should fit in a single response. Use from_ts/to_ts to narrow the time range if needed.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**ticks** | [**Array&lt;MarketTickResponse&gt;**](MarketTickResponse.md) | List of ticks (ordered by ts_wall) | [default to undefined]
**count** | **number** | Number of ticks returned | [default to undefined]

## Example

```typescript
import { HistoricalTicksResponse } from '@polytrader/api-client';

const instance: HistoricalTicksResponse = {
    ticks,
    count,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
