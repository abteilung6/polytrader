# StrategyOrderItem

Single order record for strategy-scoped orders API.  Mirrors OrderCreatedEvent + intent (order_id, ts_wall, market, side, size, status). execution_mode indicates paper vs live so UI can show Paper/Live badge.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**order_id** | **string** | Internal order UUID | [default to undefined]
**client_order_id** | **string** | Idempotency key | [default to undefined]
**ts_wall** | **string** | Wall-clock time (UTC, ISO 8601) | [default to undefined]
**market_slug** | **string** | Market identifier | [default to undefined]
**side** | **string** | Trade side: BUY or SELL | [default to undefined]
**size** | **number** | Order size in USD | [default to undefined]
**limit_price** | **number** | Limit price (0-1 range) | [default to undefined]
**status** | **string** | Order status (e.g. PENDING_SUBMIT, LIVE, FILLED, REJECTED) | [default to undefined]
**execution_mode** | **string** | Paper or live execution; UI shows Paper/Live badge | [default to undefined]

## Example

```typescript
import { StrategyOrderItem } from '@polytrader/api-client';

const instance: StrategyOrderItem = {
    order_id,
    client_order_id,
    ts_wall,
    market_slug,
    side,
    size,
    limit_price,
    status,
    execution_mode,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
