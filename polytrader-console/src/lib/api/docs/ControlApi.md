# ControlApi

All URIs are relative to *http://localhost*

|Method | HTTP request | Description|
|------------- | ------------- | -------------|
|[**activateKillSwitchApiV1CommandsExecutionKillSwitchPost**](#activatekillswitchapiv1commandsexecutionkillswitchpost) | **POST** /api/v1/commands/execution/kill-switch | Activate Kill Switch|
|[**activateStrategyApiV1CommandsLiveStrategiesStrategyIdActivatePost**](#activatestrategyapiv1commandslivestrategiesstrategyidactivatepost) | **POST** /api/v1/commands/live-strategies/{strategy_id}/activate | Activate Strategy|
|[**createStrategyApiV1CommandsStrategiesPost**](#createstrategyapiv1commandsstrategiespost) | **POST** /api/v1/commands/strategies | Create Strategy|
|[**deactivateStrategyApiV1CommandsLiveStrategiesStrategyIdDeactivatePost**](#deactivatestrategyapiv1commandslivestrategiesstrategyiddeactivatepost) | **POST** /api/v1/commands/live-strategies/{strategy_id}/deactivate | Deactivate Strategy|
|[**disableExecutionApiV1CommandsExecutionDisablePost**](#disableexecutionapiv1commandsexecutiondisablepost) | **POST** /api/v1/commands/execution/disable | Disable Execution|
|[**enableExecutionApiV1CommandsExecutionEnablePost**](#enableexecutionapiv1commandsexecutionenablepost) | **POST** /api/v1/commands/execution/enable | Enable Execution|
|[**getCommandStatusApiV1StateCommandsCommandIdGet**](#getcommandstatusapiv1statecommandscommandidget) | **GET** /api/v1/state/commands/{command_id} | Get Command Status|
|[**getExecutionStateApiV1StateExecutionGet**](#getexecutionstateapiv1stateexecutionget) | **GET** /api/v1/state/execution | Get Execution State|
|[**getHealthApiV1StateHealthGet**](#gethealthapiv1statehealthget) | **GET** /api/v1/state/health | Get Health|
|[**getLiveStrategiesApiV1StateLiveStrategiesGet**](#getlivestrategiesapiv1statelivestrategiesget) | **GET** /api/v1/state/live-strategies | Get Live Strategies|
|[**getPerformanceOverviewApiV1StateStrategiesPerformanceOverviewGet**](#getperformanceoverviewapiv1statestrategiesperformanceoverviewget) | **GET** /api/v1/state/strategies/performance/overview | Get Performance Overview|
|[**getStrategiesApiV1StateStrategiesGet**](#getstrategiesapiv1statestrategiesget) | **GET** /api/v1/state/strategies | Get Strategies|
|[**getStrategyByIdApiV1StateStrategiesStrategyIdGet**](#getstrategybyidapiv1statestrategiesstrategyidget) | **GET** /api/v1/state/strategies/{strategy_id} | Get Strategy By Id|
|[**getStrategyOrdersApiV1StateStrategiesStrategyIdOrdersGet**](#getstrategyordersapiv1statestrategiesstrategyidordersget) | **GET** /api/v1/state/strategies/{strategy_id}/orders | Get Strategy Orders|
|[**getStrategyPerformanceApiV1StateStrategiesStrategyIdPerformanceGet**](#getstrategyperformanceapiv1statestrategiesstrategyidperformanceget) | **GET** /api/v1/state/strategies/{strategy_id}/performance | Get Strategy Performance|
|[**getStrategySignalsApiV1StateStrategiesStrategyIdSignalsGet**](#getstrategysignalsapiv1statestrategiesstrategyidsignalsget) | **GET** /api/v1/state/strategies/{strategy_id}/signals | Get Strategy Signals|
|[**getStrategyTemplateApiV1StateStrategiesTemplatesTypeIdGet**](#getstrategytemplateapiv1statestrategiestemplatestypeidget) | **GET** /api/v1/state/strategies/templates/{type_id} | Get Strategy Template|
|[**getStrategyTemplateVersionApiV1StateStrategiesTemplatesTypeIdVersionsVersionGet**](#getstrategytemplateversionapiv1statestrategiestemplatestypeidversionsversionget) | **GET** /api/v1/state/strategies/templates/{type_id}/versions/{version} | Get Strategy Template Version|
|[**listStrategyTemplatesApiV1StateStrategiesTemplatesGet**](#liststrategytemplatesapiv1statestrategiestemplatesget) | **GET** /api/v1/state/strategies/templates | List Strategy Templates|
|[**resetKillSwitchApiV1CommandsExecutionKillSwitchResetPost**](#resetkillswitchapiv1commandsexecutionkillswitchresetpost) | **POST** /api/v1/commands/execution/kill-switch/reset | Reset Kill Switch|
|[**updateStrategyApiV1CommandsStrategiesStrategyIdPatch**](#updatestrategyapiv1commandsstrategiesstrategyidpatch) | **PATCH** /api/v1/commands/strategies/{strategy_id} | Update Strategy|
|[**validateStrategyConfigApiV1StateStrategiesValidatePost**](#validatestrategyconfigapiv1statestrategiesvalidatepost) | **POST** /api/v1/state/strategies/validate | Validate Strategy Config|

# **activateKillSwitchApiV1CommandsExecutionKillSwitchPost**
> CommandEnvelopeResponse activateKillSwitchApiV1CommandsExecutionKillSwitchPost(killSwitchRequest)

Activate kill switch (emergency stop — immediate, not queued).  Per flows.mdc §13: Kill switch provides immediate stop-trading policy. This endpoint directly applies the kill switch to in-memory state, disables execution in the DB, and creates an audit command record.  Unlike enable/disable which go through the command queue, the kill switch is applied immediately because it is a safety-critical emergency action.  After activation: - execution_enabled = false - kill_switch_active = true - KillSwitchEvent emitted - All pending orders will be rejected by execution router  Reset requires a separate call to /commands/execution/kill-switch/reset followed by /commands/execution/enable.

### Example

```typescript
import {
    ControlApi,
    Configuration,
    KillSwitchRequest
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

let killSwitchRequest: KillSwitchRequest; //

const { status, data } = await apiInstance.activateKillSwitchApiV1CommandsExecutionKillSwitchPost(
    killSwitchRequest
);
```

### Parameters

|Name | Type | Description  | Notes|
|------------- | ------------- | ------------- | -------------|
| **killSwitchRequest** | **KillSwitchRequest**|  | |


### Return type

**CommandEnvelopeResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |
|**400** | Validation error |  -  |
|**503** | Platform not running |  -  |
|**422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **activateStrategyApiV1CommandsLiveStrategiesStrategyIdActivatePost**
> CommandEnvelopeResponse activateStrategyApiV1CommandsLiveStrategiesStrategyIdActivatePost(activateStrategyRequest)

Activate strategy for live trading (creates command in queue).  Idempotent: If client_request_id already exists, returns existing command_id.

### Example

```typescript
import {
    ControlApi,
    Configuration,
    ActivateStrategyRequest
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

let strategyId: string; // (default to undefined)
let activateStrategyRequest: ActivateStrategyRequest; //

const { status, data } = await apiInstance.activateStrategyApiV1CommandsLiveStrategiesStrategyIdActivatePost(
    strategyId,
    activateStrategyRequest
);
```

### Parameters

|Name | Type | Description  | Notes|
|------------- | ------------- | ------------- | -------------|
| **activateStrategyRequest** | **ActivateStrategyRequest**|  | |
| **strategyId** | [**string**] |  | defaults to undefined|


### Return type

**CommandEnvelopeResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |
|**400** | Validation error |  -  |
|**422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **createStrategyApiV1CommandsStrategiesPost**
> StrategyResponse createStrategyApiV1CommandsStrategiesPost(createStrategyRequest)

Create a new strategy in registry.  Per Commit 17: This endpoint now: - Resolves version selector to exact version - Validates config before creation - Calculates config_hash for reproducibility - Generates deployment_id for correlation - Adds reproducibility metadata (run_identity)

### Example

```typescript
import {
    ControlApi,
    Configuration,
    CreateStrategyRequest
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

let createStrategyRequest: CreateStrategyRequest; //

const { status, data } = await apiInstance.createStrategyApiV1CommandsStrategiesPost(
    createStrategyRequest
);
```

### Parameters

|Name | Type | Description  | Notes|
|------------- | ------------- | ------------- | -------------|
| **createStrategyRequest** | **CreateStrategyRequest**|  | |


### Return type

**StrategyResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**201** | Successful Response |  -  |
|**400** | Validation error |  -  |
|**409** | Strategy already exists |  -  |
|**422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **deactivateStrategyApiV1CommandsLiveStrategiesStrategyIdDeactivatePost**
> CommandEnvelopeResponse deactivateStrategyApiV1CommandsLiveStrategiesStrategyIdDeactivatePost(deactivateStrategyRequest)

Deactivate strategy for live trading (creates command in queue).  Idempotent: If client_request_id already exists, returns existing command_id.

### Example

```typescript
import {
    ControlApi,
    Configuration,
    DeactivateStrategyRequest
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

let strategyId: string; // (default to undefined)
let deactivateStrategyRequest: DeactivateStrategyRequest; //

const { status, data } = await apiInstance.deactivateStrategyApiV1CommandsLiveStrategiesStrategyIdDeactivatePost(
    strategyId,
    deactivateStrategyRequest
);
```

### Parameters

|Name | Type | Description  | Notes|
|------------- | ------------- | ------------- | -------------|
| **deactivateStrategyRequest** | **DeactivateStrategyRequest**|  | |
| **strategyId** | [**string**] |  | defaults to undefined|


### Return type

**CommandEnvelopeResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |
|**400** | Validation error |  -  |
|**422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **disableExecutionApiV1CommandsExecutionDisablePost**
> CommandEnvelopeResponse disableExecutionApiV1CommandsExecutionDisablePost(disableExecutionRequest)

Disable execution (creates command in queue).  Idempotent: If client_request_id already exists, returns existing command_id. Version check: If expected_version != current version, returns 409 Conflict.

### Example

```typescript
import {
    ControlApi,
    Configuration,
    DisableExecutionRequest
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

let disableExecutionRequest: DisableExecutionRequest; //

const { status, data } = await apiInstance.disableExecutionApiV1CommandsExecutionDisablePost(
    disableExecutionRequest
);
```

### Parameters

|Name | Type | Description  | Notes|
|------------- | ------------- | ------------- | -------------|
| **disableExecutionRequest** | **DisableExecutionRequest**|  | |


### Return type

**CommandEnvelopeResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |
|**409** | Version conflict |  -  |
|**400** | Validation error |  -  |
|**422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **enableExecutionApiV1CommandsExecutionEnablePost**
> CommandEnvelopeResponse enableExecutionApiV1CommandsExecutionEnablePost(enableExecutionRequest)

Enable execution (creates command in queue).  Idempotent: If client_request_id already exists, returns existing command_id. Version check: If expected_version != current version, returns 409 Conflict.

### Example

```typescript
import {
    ControlApi,
    Configuration,
    EnableExecutionRequest
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

let enableExecutionRequest: EnableExecutionRequest; //

const { status, data } = await apiInstance.enableExecutionApiV1CommandsExecutionEnablePost(
    enableExecutionRequest
);
```

### Parameters

|Name | Type | Description  | Notes|
|------------- | ------------- | ------------- | -------------|
| **enableExecutionRequest** | **EnableExecutionRequest**|  | |


### Return type

**CommandEnvelopeResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |
|**409** | Version conflict |  -  |
|**400** | Validation error |  -  |
|**422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getCommandStatusApiV1StateCommandsCommandIdGet**
> CommandStatusResponse getCommandStatusApiV1StateCommandsCommandIdGet()

Get command status by command_id.

### Example

```typescript
import {
    ControlApi,
    Configuration
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

let commandId: string; // (default to undefined)

const { status, data } = await apiInstance.getCommandStatusApiV1StateCommandsCommandIdGet(
    commandId
);
```

### Parameters

|Name | Type | Description  | Notes|
|------------- | ------------- | ------------- | -------------|
| **commandId** | [**string**] |  | defaults to undefined|


### Return type

**CommandStatusResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |
|**404** | Command not found |  -  |
|**422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getExecutionStateApiV1StateExecutionGet**
> ExecutionStateResponse getExecutionStateApiV1StateExecutionGet()

Get execution control state (with version for optimistic concurrency).  Includes kill_switch_active from in-memory state (not persisted in DB). When the platform is not running (exec_control is None), kill_switch_active defaults to False.

### Example

```typescript
import {
    ControlApi,
    Configuration
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

const { status, data } = await apiInstance.getExecutionStateApiV1StateExecutionGet();
```

### Parameters
This endpoint does not have any parameters.


### Return type

**ExecutionStateResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getHealthApiV1StateHealthGet**
> HealthResponse getHealthApiV1StateHealthGet()

Get system health with individual gate statuses.  Returns overall status and individual gate statuses (db, market_data_freshness, etc.). Overall status = worst gate status (down > degraded > ok).  Note: Health gates implementation is basic in this commit. Full health gate checks will be implemented in later commits.

### Example

```typescript
import {
    ControlApi,
    Configuration
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

const { status, data } = await apiInstance.getHealthApiV1StateHealthGet();
```

### Parameters
This endpoint does not have any parameters.


### Return type

**HealthResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getLiveStrategiesApiV1StateLiveStrategiesGet**
> LiveStrategiesResponse getLiveStrategiesApiV1StateLiveStrategiesGet()

Get active live strategies.

### Example

```typescript
import {
    ControlApi,
    Configuration
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

const { status, data } = await apiInstance.getLiveStrategiesApiV1StateLiveStrategiesGet();
```

### Parameters
This endpoint does not have any parameters.


### Return type

**LiveStrategiesResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getPerformanceOverviewApiV1StateStrategiesPerformanceOverviewGet**
> PerformanceOverviewResponse getPerformanceOverviewApiV1StateStrategiesPerformanceOverviewGet()

Get aggregated performance overview for all strategy instances.  Per PERFORMANCE_OVERVIEW_PROPOSAL.md §7: - DB-side aggregation on strategy_closed_trades table. - LEFT JOIN to strategy_instances for registry metadata. - Evidence tier (INSUFFICIENT_DATA / TRACKING) per trade count threshold. - Does NOT require the trader runtime process.  Query params:     since: ISO 8601 UTC lower bound on exit_ts_wall (omit for all time).     until: ISO 8601 UTC upper bound on exit_ts_wall (default: server now()).     execution_mode: Filter by paper or live (omit for all).     template_type_id: Filter by strategy template.     state: Filter by lifecycle state (RUNNING, STOPPED, etc.).     sort_by: Sort column descending (total_realized_pnl, win_rate_pct, trade_count).     limit: Max rows (1-1000, default 200).

### Example

```typescript
import {
    ControlApi,
    Configuration
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

let since: string; // (optional) (default to undefined)
let until: string; // (optional) (default to undefined)
let executionMode: 'paper' | 'live'; // (optional) (default to undefined)
let templateTypeId: string; // (optional) (default to undefined)
let state: string; // (optional) (default to undefined)
let sortBy: 'total_realized_pnl' | 'win_rate_pct' | 'trade_count'; // (optional) (default to 'total_realized_pnl')
let limit: number; // (optional) (default to 200)

const { status, data } = await apiInstance.getPerformanceOverviewApiV1StateStrategiesPerformanceOverviewGet(
    since,
    until,
    executionMode,
    templateTypeId,
    state,
    sortBy,
    limit
);
```

### Parameters

|Name | Type | Description  | Notes|
|------------- | ------------- | ------------- | -------------|
| **since** | [**string**] |  | (optional) defaults to undefined|
| **until** | [**string**] |  | (optional) defaults to undefined|
| **executionMode** | [**&#39;paper&#39; | &#39;live&#39;**]**Array<&#39;paper&#39; &#124; &#39;live&#39;>** |  | (optional) defaults to undefined|
| **templateTypeId** | [**string**] |  | (optional) defaults to undefined|
| **state** | [**string**] |  | (optional) defaults to undefined|
| **sortBy** | [**&#39;total_realized_pnl&#39; | &#39;win_rate_pct&#39; | &#39;trade_count&#39;**]**Array<&#39;total_realized_pnl&#39; &#124; &#39;win_rate_pct&#39; &#124; &#39;trade_count&#39;>** |  | (optional) defaults to 'total_realized_pnl'|
| **limit** | [**number**] |  | (optional) defaults to 200|


### Return type

**PerformanceOverviewResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |
|**422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getStrategiesApiV1StateStrategiesGet**
> StrategiesResponse getStrategiesApiV1StateStrategiesGet()

Get all strategies in registry.

### Example

```typescript
import {
    ControlApi,
    Configuration
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

const { status, data } = await apiInstance.getStrategiesApiV1StateStrategiesGet();
```

### Parameters
This endpoint does not have any parameters.


### Return type

**StrategiesResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getStrategyByIdApiV1StateStrategiesStrategyIdGet**
> StrategyResponse getStrategyByIdApiV1StateStrategiesStrategyIdGet()

Get a single strategy by ID.  Returns 404 if the strategy is not in the registry.

### Example

```typescript
import {
    ControlApi,
    Configuration
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

let strategyId: string; // (default to undefined)

const { status, data } = await apiInstance.getStrategyByIdApiV1StateStrategiesStrategyIdGet(
    strategyId
);
```

### Parameters

|Name | Type | Description  | Notes|
|------------- | ------------- | ------------- | -------------|
| **strategyId** | [**string**] |  | defaults to undefined|


### Return type

**StrategyResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |
|**404** | Strategy not found |  -  |
|**422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getStrategyOrdersApiV1StateStrategiesStrategyIdOrdersGet**
> StrategyOrdersResponse getStrategyOrdersApiV1StateStrategiesStrategyIdOrdersGet()

Get paginated orders for a strategy (newest first).  Query params: limit (default 100, max 500), cursor (optional). Returns empty list when strategy has no orders. execution_mode (paper | live) is included per row for UI badge.

### Example

```typescript
import {
    ControlApi,
    Configuration
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

let strategyId: string; // (default to undefined)
let limit: number; // (optional) (default to 100)
let cursor: string; // (optional) (default to undefined)

const { status, data } = await apiInstance.getStrategyOrdersApiV1StateStrategiesStrategyIdOrdersGet(
    strategyId,
    limit,
    cursor
);
```

### Parameters

|Name | Type | Description  | Notes|
|------------- | ------------- | ------------- | -------------|
| **strategyId** | [**string**] |  | defaults to undefined|
| **limit** | [**number**] |  | (optional) defaults to 100|
| **cursor** | [**string**] |  | (optional) defaults to undefined|


### Return type

**StrategyOrdersResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |
|**422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getStrategyPerformanceApiV1StateStrategiesStrategyIdPerformanceGet**
> PerformanceResponse getStrategyPerformanceApiV1StateStrategiesStrategyIdPerformanceGet()

Get past performance for a strategy: summary + paginated closed trades.  Query params: from_ts, to_ts (optional ts_mono range), execution_mode (paper | live | omit for all), limit (default 100, max 500), cursor. Summary is computed from the returned page of items.

### Example

```typescript
import {
    ControlApi,
    Configuration
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

let strategyId: string; // (default to undefined)
let fromTs: number; // (optional) (default to undefined)
let toTs: number; // (optional) (default to undefined)
let executionMode: 'paper' | 'live'; // (optional) (default to undefined)
let limit: number; // (optional) (default to 100)
let cursor: string; // (optional) (default to undefined)

const { status, data } = await apiInstance.getStrategyPerformanceApiV1StateStrategiesStrategyIdPerformanceGet(
    strategyId,
    fromTs,
    toTs,
    executionMode,
    limit,
    cursor
);
```

### Parameters

|Name | Type | Description  | Notes|
|------------- | ------------- | ------------- | -------------|
| **strategyId** | [**string**] |  | defaults to undefined|
| **fromTs** | [**number**] |  | (optional) defaults to undefined|
| **toTs** | [**number**] |  | (optional) defaults to undefined|
| **executionMode** | [**&#39;paper&#39; | &#39;live&#39;**]**Array<&#39;paper&#39; &#124; &#39;live&#39;>** |  | (optional) defaults to undefined|
| **limit** | [**number**] |  | (optional) defaults to 100|
| **cursor** | [**string**] |  | (optional) defaults to undefined|


### Return type

**PerformanceResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |
|**422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getStrategySignalsApiV1StateStrategiesStrategyIdSignalsGet**
> StrategySignalsResponse getStrategySignalsApiV1StateStrategiesStrategyIdSignalsGet()

Get paginated signals for a strategy (newest first).  Query params: limit (default 100, max 500), cursor (optional). Returns empty list when strategy has no signals.

### Example

```typescript
import {
    ControlApi,
    Configuration
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

let strategyId: string; // (default to undefined)
let limit: number; // (optional) (default to 100)
let cursor: string; // (optional) (default to undefined)

const { status, data } = await apiInstance.getStrategySignalsApiV1StateStrategiesStrategyIdSignalsGet(
    strategyId,
    limit,
    cursor
);
```

### Parameters

|Name | Type | Description  | Notes|
|------------- | ------------- | ------------- | -------------|
| **strategyId** | [**string**] |  | defaults to undefined|
| **limit** | [**number**] |  | (optional) defaults to 100|
| **cursor** | [**string**] |  | (optional) defaults to undefined|


### Return type

**StrategySignalsResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |
|**422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getStrategyTemplateApiV1StateStrategiesTemplatesTypeIdGet**
> StrategyTypeResponse getStrategyTemplateApiV1StateStrategiesTemplatesTypeIdGet()

Get details for a specific strategy template type.  Per Commit 15: Returns template information including all available versions and parameter schema.  Args:     type_id: Template type identifier (e.g., \"simple_threshold\")  Returns:     StrategyTypeResponse with template details  Raises:     HTTPException: 404 if template type not found

### Example

```typescript
import {
    ControlApi,
    Configuration
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

let typeId: string; // (default to undefined)

const { status, data } = await apiInstance.getStrategyTemplateApiV1StateStrategiesTemplatesTypeIdGet(
    typeId
);
```

### Parameters

|Name | Type | Description  | Notes|
|------------- | ------------- | ------------- | -------------|
| **typeId** | [**string**] |  | defaults to undefined|


### Return type

**StrategyTypeResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |
|**404** | Template not found |  -  |
|**422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **getStrategyTemplateVersionApiV1StateStrategiesTemplatesTypeIdVersionsVersionGet**
> StrategyTypeResponse getStrategyTemplateVersionApiV1StateStrategiesTemplatesTypeIdVersionsVersionGet()

Get details for a specific strategy template version.  Per Commit 15: Returns template information for a specific version including parameter schema.  Args:     type_id: Template type identifier (e.g., \"simple_threshold\")     version: Template version (e.g., \"1.0.0\")  Returns:     StrategyTypeResponse with template details (single version in available_versions)  Raises:     HTTPException: 404 if template version not found

### Example

```typescript
import {
    ControlApi,
    Configuration
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

let typeId: string; // (default to undefined)
let version: string; // (default to undefined)

const { status, data } = await apiInstance.getStrategyTemplateVersionApiV1StateStrategiesTemplatesTypeIdVersionsVersionGet(
    typeId,
    version
);
```

### Parameters

|Name | Type | Description  | Notes|
|------------- | ------------- | ------------- | -------------|
| **typeId** | [**string**] |  | defaults to undefined|
| **version** | [**string**] |  | defaults to undefined|


### Return type

**StrategyTypeResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |
|**404** | Template version not found |  -  |
|**422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **listStrategyTemplatesApiV1StateStrategiesTemplatesGet**
> StrategyTypesResponse listStrategyTemplatesApiV1StateStrategiesTemplatesGet()

List all available strategy templates.  Per Commit 15: Template discovery endpoint for clients to discover available strategy types and their versions.  Returns:     StrategyTypesResponse with list of all registered templates

### Example

```typescript
import {
    ControlApi,
    Configuration
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

const { status, data } = await apiInstance.listStrategyTemplatesApiV1StateStrategiesTemplatesGet();
```

### Parameters
This endpoint does not have any parameters.


### Return type

**StrategyTypesResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **resetKillSwitchApiV1CommandsExecutionKillSwitchResetPost**
> CommandEnvelopeResponse resetKillSwitchApiV1CommandsExecutionKillSwitchResetPost(killSwitchResetRequest)

Reset (deactivate) the kill switch.  Resetting the kill switch does NOT re-enable execution. The operator must separately call /commands/execution/enable to resume trading. This is a deliberate safety measure to prevent accidental re-enablement.  After reset: - kill_switch_active = false - execution_enabled remains false (unchanged) - KillSwitchEvent emitted (triggered=false)

### Example

```typescript
import {
    ControlApi,
    Configuration,
    KillSwitchResetRequest
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

let killSwitchResetRequest: KillSwitchResetRequest; //

const { status, data } = await apiInstance.resetKillSwitchApiV1CommandsExecutionKillSwitchResetPost(
    killSwitchResetRequest
);
```

### Parameters

|Name | Type | Description  | Notes|
|------------- | ------------- | ------------- | -------------|
| **killSwitchResetRequest** | **KillSwitchResetRequest**|  | |


### Return type

**CommandEnvelopeResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |
|**400** | Validation error |  -  |
|**503** | Platform not running |  -  |
|**422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **updateStrategyApiV1CommandsStrategiesStrategyIdPatch**
> StrategyResponse updateStrategyApiV1CommandsStrategiesStrategyIdPatch(updateStrategyRequest)

Update an existing strategy in registry.

### Example

```typescript
import {
    ControlApi,
    Configuration,
    UpdateStrategyRequest
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

let strategyId: string; // (default to undefined)
let updateStrategyRequest: UpdateStrategyRequest; //

const { status, data } = await apiInstance.updateStrategyApiV1CommandsStrategiesStrategyIdPatch(
    strategyId,
    updateStrategyRequest
);
```

### Parameters

|Name | Type | Description  | Notes|
|------------- | ------------- | ------------- | -------------|
| **updateStrategyRequest** | **UpdateStrategyRequest**|  | |
| **strategyId** | [**string**] |  | defaults to undefined|


### Return type

**StrategyResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |
|**404** | Strategy not found |  -  |
|**400** | Validation error |  -  |
|**422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **validateStrategyConfigApiV1StateStrategiesValidatePost**
> ValidateStrategyConfigResponse validateStrategyConfigApiV1StateStrategiesValidatePost(validateStrategyConfigRequest)

Validate a strategy configuration against a template schema.  Per Commit 16: This endpoint allows clients to validate configurations before creating strategy instances. Returns validation results with clear error messages.  Args:     request: Validation request with template_type_id, version_selector, and config  Returns:     ValidateStrategyConfigResponse with validation results  Raises:     HTTPException: 400 if template not found or version resolution fails

### Example

```typescript
import {
    ControlApi,
    Configuration,
    ValidateStrategyConfigRequest
} from '@polytrader/api-client';

const configuration = new Configuration();
const apiInstance = new ControlApi(configuration);

let validateStrategyConfigRequest: ValidateStrategyConfigRequest; //

const { status, data } = await apiInstance.validateStrategyConfigApiV1StateStrategiesValidatePost(
    validateStrategyConfigRequest
);
```

### Parameters

|Name | Type | Description  | Notes|
|------------- | ------------- | ------------- | -------------|
| **validateStrategyConfigRequest** | **ValidateStrategyConfigRequest**|  | |


### Return type

**ValidateStrategyConfigResponse**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
|**200** | Successful Response |  -  |
|**400** | Template not found or version resolution failed |  -  |
|**422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

