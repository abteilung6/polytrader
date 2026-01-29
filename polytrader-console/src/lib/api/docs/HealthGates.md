# HealthGates

All health gates status.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**db** | [**HealthGateStatus**](HealthGateStatus.md) | Database connectivity | [default to undefined]
**market_data_freshness** | [**HealthGateStatus**](HealthGateStatus.md) | Market data staleness check | [default to undefined]
**event_bus_lag** | [**HealthGateStatus**](HealthGateStatus.md) | Event bus processing lag | [default to undefined]
**venue_connectivity** | [**HealthGateStatus**](HealthGateStatus.md) | Venue API connectivity | [default to undefined]
**risk_engine** | [**HealthGateStatus**](HealthGateStatus.md) | Risk engine health | [default to undefined]
**clock_skew_ms** | **number** | Clock skew in milliseconds | [default to undefined]

## Example

```typescript
import { HealthGates } from '@polytrader/api-client';

const instance: HealthGates = {
    db,
    market_data_freshness,
    event_bus_lag,
    venue_connectivity,
    risk_engine,
    clock_skew_ms,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
