import { useQuery } from '@tanstack/react-query'

import { controlApi } from '@/lib/api-client'
import type { StrategyTypesResponse } from '@/lib/api'

export const QUERY_KEY_STRATEGY_TEMPLATES = ['strategy-templates'] as const

export const useStrategyTemplatesQuery = () =>
  useQuery({
    queryKey: QUERY_KEY_STRATEGY_TEMPLATES,
    queryFn: async (): Promise<StrategyTypesResponse> => {
      const response = await controlApi.listStrategyTemplatesApiV1StateStrategiesTemplatesGet()
      return response.data
    },
  })
