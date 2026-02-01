# StrategySignalItem

Single signal record for strategy-scoped signals API.  Mirrors SignalEvent fields (event_id, ts_wall, market, scores).

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**event_id** | **string** | Event identifier (UUID) | [default to undefined]
**ts_wall** | **string** | Wall-clock time (UTC, ISO 8601) | [default to undefined]
**market_slug** | **string** | Market identifier | [default to undefined]
**outcome** | **string** | Outcome: UP or DOWN | [default to undefined]
**p_up** | **number** | Probability UP wins | [default to undefined]
**p_down** | **number** | Probability DOWN wins | [default to undefined]
**edge** | **number** | Edge/confidence score | [default to undefined]
**confidence** | **number** | Confidence level | [default to undefined]
**model_id** | **string** | Strategy/model identifier | [default to undefined]
**model_version** | **string** | Model version | [default to undefined]
**snapshot_hash** | **string** |  | [optional] [default to undefined]
**rationale** | **string** |  | [optional] [default to undefined]

## Example

```typescript
import { StrategySignalItem } from '@polytrader/api-client';

const instance: StrategySignalItem = {
    event_id,
    ts_wall,
    market_slug,
    outcome,
    p_up,
    p_down,
    edge,
    confidence,
    model_id,
    model_version,
    snapshot_hash,
    rationale,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
