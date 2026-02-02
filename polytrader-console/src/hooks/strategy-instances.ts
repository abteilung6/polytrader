import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { controlApi } from '@/lib/api-client'
import type { StrategiesResponse } from '@/lib/api'

export const QUERY_KEY_STRATEGY_INSTANCES = ['strategy-instances'] as const

export const useStrategyInstancesQuery = () =>
  useQuery({
    queryKey: QUERY_KEY_STRATEGY_INSTANCES,
    queryFn: async (): Promise<StrategiesResponse> => {
      const response = await controlApi.getStrategiesApiV1StateStrategiesGet()
      return response.data
    },
  })

export function useActivateStrategy(strategyId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      await controlApi.activateStrategyApiV1CommandsLiveStrategiesStrategyIdActivatePost({
        strategyId,
        activateStrategyRequest: {
          reason: 'Enable from console',
          issued_by: 'operator',
          client_request_id: `enable-${strategyId}-${Date.now()}`,
        },
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY_STRATEGY_INSTANCES })
    },
  })
}

export function useDeactivateStrategy(strategyId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      await controlApi.deactivateStrategyApiV1CommandsLiveStrategiesStrategyIdDeactivatePost({
        strategyId,
        deactivateStrategyRequest: {
          reason: 'Disable from console',
          issued_by: 'operator',
          client_request_id: `disable-${strategyId}-${Date.now()}`,
        },
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY_STRATEGY_INSTANCES })
    },
  })
}
