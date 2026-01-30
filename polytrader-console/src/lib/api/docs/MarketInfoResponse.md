# MarketInfoResponse

Market information response.  Represents a market/outcome pair with latest tick timestamp, active status, and optional market window start/end (derived from slug).

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**market_slug** | **string** | Market identifier | [default to undefined]
**outcome** | **string** | Market outcome: UP or DOWN | [default to undefined]
**latest_tick_ts** | **string** |  | [default to undefined]
**active** | **boolean** | Whether market is currently active (current window) | [default to undefined]
**start_date** | **string** |  | [optional] [default to undefined]
**end_date** | **string** |  | [optional] [default to undefined]

## Example

```typescript
import { MarketInfoResponse } from '@polytrader/api-client';

const instance: MarketInfoResponse = {
    market_slug,
    outcome,
    latest_tick_ts,
    active,
    start_date,
    end_date,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
