import { useQuery } from '@tanstack/react-query'

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
