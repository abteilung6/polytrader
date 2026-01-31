# ControlApi

All URIs are relative to *http://localhost*

|Method | HTTP request | Description|
|------------- | ------------- | -------------|
|[**activateStrategyApiV1CommandsLiveStrategiesStrategyIdActivatePost**](#activatestrategyapiv1commandslivestrategiesstrategyidactivatepost) | **POST** /api/v1/commands/live-strategies/{strategy_id}/activate | Activate Strategy|
|[**createStrategyApiV1CommandsStrategiesPost**](#createstrategyapiv1commandsstrategiespost) | **POST** /api/v1/commands/strategies | Create Strategy|
|[**deactivateStrategyApiV1CommandsLiveStrategiesStrategyIdDeactivatePost**](#deactivatestrategyapiv1commandslivestrategiesstrategyiddeactivatepost) | **POST** /api/v1/commands/live-strategies/{strategy_id}/deactivate | Deactivate Strategy|
|[**disableExecutionApiV1CommandsExecutionDisablePost**](#disableexecutionapiv1commandsexecutiondisablepost) | **POST** /api/v1/commands/execution/disable | Disable Execution|
|[**enableExecutionApiV1CommandsExecutionEnablePost**](#enableexecutionapiv1commandsexecutionenablepost) | **POST** /api/v1/commands/execution/enable | Enable Execution|
|[**getCommandStatusApiV1StateCommandsCommandIdGet**](#getcommandstatusapiv1statecommandscommandidget) | **GET** /api/v1/state/commands/{command_id} | Get Command Status|
|[**getExecutionStateApiV1StateExecutionGet**](#getexecutionstateapiv1stateexecutionget) | **GET** /api/v1/state/execution | Get Execution State|
|[**getHealthApiV1StateHealthGet**](#gethealthapiv1statehealthget) | **GET** /api/v1/state/health | Get Health|
|[**getLiveStrategiesApiV1StateLiveStrategiesGet**](#getlivestrategiesapiv1statelivestrategiesget) | **GET** /api/v1/state/live-strategies | Get Live Strategies|
|[**getStrategiesApiV1StateStrategiesGet**](#getstrategiesapiv1statestrategiesget) | **GET** /api/v1/state/strategies | Get Strategies|
|[**getStrategyByIdApiV1StateStrategiesStrategyIdGet**](#getstrategybyidapiv1statestrategiesstrategyidget) | **GET** /api/v1/state/strategies/{strategy_id} | Get Strategy By Id|
|[**getStrategyOrdersApiV1StateStrategiesStrategyIdOrdersGet**](#getstrategyordersapiv1statestrategiesstrategyidordersget) | **GET** /api/v1/state/strategies/{strategy_id}/orders | Get Strategy Orders|
|[**getStrategySignalsApiV1StateStrategiesStrategyIdSignalsGet**](#getstrategysignalsapiv1statestrategiesstrategyidsignalsget) | **GET** /api/v1/state/strategies/{strategy_id}/signals | Get Strategy Signals|
|[**getStrategyTemplateApiV1StateStrategiesTemplatesTypeIdGet**](#getstrategytemplateapiv1statestrategiestemplatestypeidget) | **GET** /api/v1/state/strategies/templates/{type_id} | Get Strategy Template|
|[**getStrategyTemplateVersionApiV1StateStrategiesTemplatesTypeIdVersionsVersionGet**](#getstrategytemplateversionapiv1statestrategiestemplatestypeidversionsversionget) | **GET** /api/v1/state/strategies/templates/{type_id}/versions/{version} | Get Strategy Template Version|
|[**listStrategyTemplatesApiV1StateStrategiesTemplatesGet**](#liststrategytemplatesapiv1statestrategiestemplatesget) | **GET** /api/v1/state/strategies/templates | List Strategy Templates|
|[**updateStrategyApiV1CommandsStrategiesStrategyIdPatch**](#updatestrategyapiv1commandsstrategiesstrategyidpatch) | **PATCH** /api/v1/commands/strategies/{strategy_id} | Update Strategy|
|[**validateStrategyConfigApiV1StateStrategiesValidatePost**](#validatestrategyconfigapiv1statestrategiesvalidatepost) | **POST** /api/v1/state/strategies/validate | Validate Strategy Config|

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

Get execution control state (with version for optimistic concurrency).

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

