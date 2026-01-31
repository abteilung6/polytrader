## @polytrader/api-client@1.0.0

This generator creates TypeScript/JavaScript client that utilizes [axios](https://github.com/axios/axios). The generated Node module can be used in the following environments:

Environment
* Node.js
* Webpack
* Browserify

Language level
* ES5 - you must have a Promises/A+ library installed
* ES6

Module system
* CommonJS
* ES6 module system

It can be used in both TypeScript and JavaScript. In TypeScript, the definition will be automatically resolved via `package.json`. ([Reference](https://www.typescriptlang.org/docs/handbook/declaration-files/consumption.html))

### Building

To build and compile the typescript sources to javascript use:
```
npm install
npm run build
```

### Publishing

First build the package then run `npm publish`

### Consuming

navigate to the folder of your consuming project and run one of the following commands.

_published:_

```
npm install @polytrader/api-client@1.0.0 --save
```

_unPublished (not recommended):_

```
npm install PATH_TO_GENERATED_PACKAGE --save
```

### Documentation for API Endpoints

All URIs are relative to *http://localhost*

Class | Method | HTTP request | Description
------------ | ------------- | ------------- | -------------
*ControlApi* | [**activateStrategyApiV1CommandsLiveStrategiesStrategyIdActivatePost**](docs/ControlApi.md#activatestrategyapiv1commandslivestrategiesstrategyidactivatepost) | **POST** /api/v1/commands/live-strategies/{strategy_id}/activate | Activate Strategy
*ControlApi* | [**createStrategyApiV1CommandsStrategiesPost**](docs/ControlApi.md#createstrategyapiv1commandsstrategiespost) | **POST** /api/v1/commands/strategies | Create Strategy
*ControlApi* | [**deactivateStrategyApiV1CommandsLiveStrategiesStrategyIdDeactivatePost**](docs/ControlApi.md#deactivatestrategyapiv1commandslivestrategiesstrategyiddeactivatepost) | **POST** /api/v1/commands/live-strategies/{strategy_id}/deactivate | Deactivate Strategy
*ControlApi* | [**disableExecutionApiV1CommandsExecutionDisablePost**](docs/ControlApi.md#disableexecutionapiv1commandsexecutiondisablepost) | **POST** /api/v1/commands/execution/disable | Disable Execution
*ControlApi* | [**enableExecutionApiV1CommandsExecutionEnablePost**](docs/ControlApi.md#enableexecutionapiv1commandsexecutionenablepost) | **POST** /api/v1/commands/execution/enable | Enable Execution
*ControlApi* | [**getCommandStatusApiV1StateCommandsCommandIdGet**](docs/ControlApi.md#getcommandstatusapiv1statecommandscommandidget) | **GET** /api/v1/state/commands/{command_id} | Get Command Status
*ControlApi* | [**getExecutionStateApiV1StateExecutionGet**](docs/ControlApi.md#getexecutionstateapiv1stateexecutionget) | **GET** /api/v1/state/execution | Get Execution State
*ControlApi* | [**getHealthApiV1StateHealthGet**](docs/ControlApi.md#gethealthapiv1statehealthget) | **GET** /api/v1/state/health | Get Health
*ControlApi* | [**getLiveStrategiesApiV1StateLiveStrategiesGet**](docs/ControlApi.md#getlivestrategiesapiv1statelivestrategiesget) | **GET** /api/v1/state/live-strategies | Get Live Strategies
*ControlApi* | [**getStrategiesApiV1StateStrategiesGet**](docs/ControlApi.md#getstrategiesapiv1statestrategiesget) | **GET** /api/v1/state/strategies | Get Strategies
*ControlApi* | [**getStrategyByIdApiV1StateStrategiesStrategyIdGet**](docs/ControlApi.md#getstrategybyidapiv1statestrategiesstrategyidget) | **GET** /api/v1/state/strategies/{strategy_id} | Get Strategy By Id
*ControlApi* | [**getStrategyOrdersApiV1StateStrategiesStrategyIdOrdersGet**](docs/ControlApi.md#getstrategyordersapiv1statestrategiesstrategyidordersget) | **GET** /api/v1/state/strategies/{strategy_id}/orders | Get Strategy Orders
*ControlApi* | [**getStrategySignalsApiV1StateStrategiesStrategyIdSignalsGet**](docs/ControlApi.md#getstrategysignalsapiv1statestrategiesstrategyidsignalsget) | **GET** /api/v1/state/strategies/{strategy_id}/signals | Get Strategy Signals
*ControlApi* | [**getStrategyTemplateApiV1StateStrategiesTemplatesTypeIdGet**](docs/ControlApi.md#getstrategytemplateapiv1statestrategiestemplatestypeidget) | **GET** /api/v1/state/strategies/templates/{type_id} | Get Strategy Template
*ControlApi* | [**getStrategyTemplateVersionApiV1StateStrategiesTemplatesTypeIdVersionsVersionGet**](docs/ControlApi.md#getstrategytemplateversionapiv1statestrategiestemplatestypeidversionsversionget) | **GET** /api/v1/state/strategies/templates/{type_id}/versions/{version} | Get Strategy Template Version
*ControlApi* | [**listStrategyTemplatesApiV1StateStrategiesTemplatesGet**](docs/ControlApi.md#liststrategytemplatesapiv1statestrategiestemplatesget) | **GET** /api/v1/state/strategies/templates | List Strategy Templates
*ControlApi* | [**updateStrategyApiV1CommandsStrategiesStrategyIdPatch**](docs/ControlApi.md#updatestrategyapiv1commandsstrategiesstrategyidpatch) | **PATCH** /api/v1/commands/strategies/{strategy_id} | Update Strategy
*ControlApi* | [**validateStrategyConfigApiV1StateStrategiesValidatePost**](docs/ControlApi.md#validatestrategyconfigapiv1statestrategiesvalidatepost) | **POST** /api/v1/state/strategies/validate | Validate Strategy Config
*MarketApi* | [**getHistoricalTicksApiV1MarketTicksHistoryGet**](docs/MarketApi.md#gethistoricalticksapiv1markettickshistoryget) | **GET** /api/v1/market/ticks/history | Get Historical Ticks
*MarketApi* | [**getLatestTickApiV1MarketTicksLatestGet**](docs/MarketApi.md#getlatesttickapiv1markettickslatestget) | **GET** /api/v1/market/ticks/latest | Get Latest Tick
*MarketApi* | [**getMarketsApiV1MarketMarketsGet**](docs/MarketApi.md#getmarketsapiv1marketmarketsget) | **GET** /api/v1/market/markets | Get Markets


### Documentation For Models

 - [ActivateStrategyRequest](docs/ActivateStrategyRequest.md)
 - [CommandEnvelopeResponse](docs/CommandEnvelopeResponse.md)
 - [CommandStatusResponse](docs/CommandStatusResponse.md)
 - [CreateStrategyRequest](docs/CreateStrategyRequest.md)
 - [DeactivateStrategyRequest](docs/DeactivateStrategyRequest.md)
 - [DisableExecutionRequest](docs/DisableExecutionRequest.md)
 - [EnableExecutionRequest](docs/EnableExecutionRequest.md)
 - [ErrorResponse](docs/ErrorResponse.md)
 - [ExecutionStateResponse](docs/ExecutionStateResponse.md)
 - [HTTPValidationError](docs/HTTPValidationError.md)
 - [HealthGateStatus](docs/HealthGateStatus.md)
 - [HealthGates](docs/HealthGates.md)
 - [HealthResponse](docs/HealthResponse.md)
 - [HistoricalTicksResponse](docs/HistoricalTicksResponse.md)
 - [LiveStrategiesResponse](docs/LiveStrategiesResponse.md)
 - [LocationInner](docs/LocationInner.md)
 - [MarketInfoResponse](docs/MarketInfoResponse.md)
 - [MarketTickResponse](docs/MarketTickResponse.md)
 - [MarketsResponse](docs/MarketsResponse.md)
 - [RunIdentityResponse](docs/RunIdentityResponse.md)
 - [StrategiesResponse](docs/StrategiesResponse.md)
 - [StrategyOrderItem](docs/StrategyOrderItem.md)
 - [StrategyOrdersResponse](docs/StrategyOrdersResponse.md)
 - [StrategyResponse](docs/StrategyResponse.md)
 - [StrategySignalItem](docs/StrategySignalItem.md)
 - [StrategySignalsResponse](docs/StrategySignalsResponse.md)
 - [StrategyTypeResponse](docs/StrategyTypeResponse.md)
 - [StrategyTypesResponse](docs/StrategyTypesResponse.md)
 - [UpdateStrategyRequest](docs/UpdateStrategyRequest.md)
 - [ValidateStrategyConfigRequest](docs/ValidateStrategyConfigRequest.md)
 - [ValidateStrategyConfigResponse](docs/ValidateStrategyConfigResponse.md)
 - [ValidationError](docs/ValidationError.md)
 - [VersionConflictResponse](docs/VersionConflictResponse.md)
 - [VersionSelectorRequest](docs/VersionSelectorRequest.md)


<a id="documentation-for-authorization"></a>
## Documentation For Authorization

Endpoints do not require authorization.

