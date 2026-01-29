# MarketApi

All URIs are relative to *http://localhost*

|Method | HTTP request | Description|
|------------- | ------------- | -------------|
|[**getHistoricalTicksApiV1MarketTicksHistoryGet**](#gethistoricalticksapiv1markettickshistoryget) | **GET** /api/v1/market/ticks/history | Get Historical Ticks|
|[**getLatestTickApiV1MarketTicksLatestGet**](#getlatesttickapiv1markettickslatestget) | **GET** /api/v1/market/ticks/latest | Get Latest Tick|
|[**getMarketsApiV1MarketMarketsGet**](#getmarketsapiv1marketmarketsget) | **GET** /api/v1/market/markets | Get Markets|

# **getHistoricalTicksApiV1MarketTicksHistoryGet**
> HistoricalTicksResponse getHistoricalTicksApiV1MarketTicksHistoryGet()

Get historical ticks for a market/outcome.  Returns a list of market ticks for the specified market and outcome, optionally filtered by time range. Used for charting and historical analysis.  Args:     request: FastAPI request (for correlation ID)     market_slug: Market identifier (e.g., \"btc-updown-15m-1767900600\")     outcome: Market outcome (\"UP\" or \"DOWN\")     from_ts: Start timestamp (inclusive, optional)     to_ts: End timestamp (inclusive, optional)     limit: Maximum number of ticks to return (default: 5000, max: 10000)     repository: MarketTickRepository (injected via FastAPI)  Returns:     HistoricalTicksResponse with list of ticks and count  Raises:     HTTPException: 400 if outcome is invalid, 500 on database error  Note:     - For a 15-minute market window, all ticks should typically fit within the default limit     - Ticks are ordered by ts_wall ascending, ts_mono ascending     - Use from_ts/to_ts to narrow the time range if needed

### Example

```typescript
import {
    MarketApi,
    Configuration
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new MarketApi(configuration);

let marketSlug: string; //Market identifier (e.g., \'btc-updown-15m-1767900600\') (default to undefined)
let outcome: string; //Market outcome: UP or DOWN (default to undefined)
let fromTs: string; //Start timestamp (ISO 8601 UTC, inclusive) (optional) (default to undefined)
let toTs: string; //End timestamp (ISO 8601 UTC, inclusive) (optional) (default to undefined)
let limit: number; //Maximum number of ticks to return (optional) (default to 5000)

const { status, data } = await apiInstance.getHistoricalTicksApiV1MarketTicksHistoryGet(
    marketSlug,
    outcome,
    fromTs,
    toTs,
    limit
);
```

### Parameters

|Name | Type | Description  | Notes|
|------------- | ------------- | ------------- | -------------|
| **marketSlug** | [**string**] | Market identifier (e.g., \&#39;btc-updown-15m-1767900600\&#39;) | defaults to undefined|
| **outcome** | [**string**] | Market outcome: UP or DOWN | defaults to undefined|
| **fromTs** | [**string**] | Start timestamp (ISO 8601 UTC, inclusive) | (optional) defaults to undefined|
| **toTs** | [**string**] | End timestamp (ISO 8601 UTC, inclusive) | (optional) defaults to undefined|
| **limit** | [**number**] | Maximum number of ticks to return | (optional) defaults to 5000|


### Return type

**HistoricalTicksResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |
|**400** | Invalid parameters |  -  |
|**500** | Internal server error |  -  |
|**422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getLatestTickApiV1MarketTicksLatestGet**
> MarketTickResponse getLatestTickApiV1MarketTicksLatestGet()

Get latest tick for a market/outcome.  Returns the most recent market tick for the specified market and outcome. Used for quick price checks and initial UI state.  Args:     request: FastAPI request (for correlation ID)     market_slug: Market identifier (e.g., \"btc-updown-15m-1767900600\")     outcome: Market outcome (\"UP\" or \"DOWN\")     repository: MarketTickRepository (injected via FastAPI)  Returns:     MarketTickResponse with latest tick data  Raises:     HTTPException: 400 if outcome is invalid, 404 if no data found, 500 on database error

### Example

```typescript
import {
    MarketApi,
    Configuration
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new MarketApi(configuration);

let marketSlug: string; //Market identifier (e.g., \'btc-updown-15m-1767900600\') (default to undefined)
let outcome: string; //Market outcome: UP or DOWN (default to undefined)

const { status, data } = await apiInstance.getLatestTickApiV1MarketTicksLatestGet(
    marketSlug,
    outcome
);
```

### Parameters

|Name | Type | Description  | Notes|
|------------- | ------------- | ------------- | -------------|
| **marketSlug** | [**string**] | Market identifier (e.g., \&#39;btc-updown-15m-1767900600\&#39;) | defaults to undefined|
| **outcome** | [**string**] | Market outcome: UP or DOWN | defaults to undefined|


### Return type

**MarketTickResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |
|**400** | Invalid parameters |  -  |
|**404** | Market/outcome not found |  -  |
|**500** | Internal server error |  -  |
|**422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getMarketsApiV1MarketMarketsGet**
> MarketsResponse getMarketsApiV1MarketMarketsGet()

Get list of available markets.  Returns a list of all markets with tick data, optionally filtered by pattern and active status. Markets are ordered by latest_tick_ts descending (newest first).  Args:     request: FastAPI request (for correlation ID)     pattern: Market pattern filter (e.g., \"btc-updown-15m\", optional)     active_only: If true, only return active markets (default: false)     repository: MarketTickRepository (injected via FastAPI)  Returns:     MarketsResponse with list of markets and count  Raises:     HTTPException: 500 on database error  Note:     - Markets are ordered by latest_tick_ts descending (newest first)     - Markets with null latest_tick_ts appear last     - Active status is determined by comparing market window start to current window start

### Example

```typescript
import {
    MarketApi,
    Configuration
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new MarketApi(configuration);

let pattern: string; //Market pattern filter (e.g., \'btc-updown-15m\') (optional) (default to undefined)
let activeOnly: boolean; //Filter to only active markets (optional) (default to false)

const { status, data } = await apiInstance.getMarketsApiV1MarketMarketsGet(
    pattern,
    activeOnly
);
```

### Parameters

|Name | Type | Description  | Notes|
|------------- | ------------- | ------------- | -------------|
| **pattern** | [**string**] | Market pattern filter (e.g., \&#39;btc-updown-15m\&#39;) | (optional) defaults to undefined|
| **activeOnly** | [**boolean**] | Filter to only active markets | (optional) defaults to false|


### Return type

**MarketsResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |
|**500** | Internal server error |  -  |
|**422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

