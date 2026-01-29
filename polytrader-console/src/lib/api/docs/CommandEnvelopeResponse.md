# CommandEnvelopeResponse

Command envelope response (standardized for all commands).

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**command_id** | **string** | Command identifier (UUID) | [default to undefined]
**status** | **string** | Command status | [default to undefined]
**submitted_at** | **string** | Command submission timestamp | [default to undefined]
**links** | **{ [key: string]: string; }** | Related resource links | [optional] [default to undefined]

## Example

```typescript
import { CommandEnvelopeResponse } from '@polytrader/api-client';

const instance: CommandEnvelopeResponse = {
    command_id,
    status,
    submitted_at,
    links,
};
```

[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)
