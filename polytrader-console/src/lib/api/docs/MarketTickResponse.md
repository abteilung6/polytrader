# MarketTickResponse

Market tick response model.  Represents a single market tick with price data and timestamps. Used for both latest tick and historical ticks endpoints.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**tick_id** | **string** | Unique tick identifier | [default to undefined]
**ts_wall** | **string** | Wall-clock timestamp (UTC) | [default to undefined]
**ts_mono** | **number** | Monotonic timestamp | [default to undefined]
**market_slug** | **string** | Market identifier | [default to undefined]
**outcome** | **string** | Market outcome: UP or DOWN | [default to undefined]
**best_bid** | **string** | Best bid price (0-1 range) | [default to undefined]
**best_ask** | **string** | Best ask price (0-1 range) | [default to undefined]
**mid** | **string** | Mid-market price | [default to undefined]
**spread** | **string** | Bid-ask spread | [default to undefined]
**spread_bps** | **string** | Spread in basis points | [default to undefined]

## Example

```typescript
import { MarketTickResponse } from '@polytrader/api-client';

const instance: MarketTickResponse = {
    tick_id,
    ts_wall,
    ts_mono,
    market_slug,
    outcome,
    best_bid,
    best_ask,
    mid,
    spread,
    spread_bps,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
