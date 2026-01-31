import { useQuery } from '@tanstack/react-query'

import { controlApi } from '@/lib/api-client'
import type { StrategyResponse } from '@/lib/api'

export const QUERY_KEY_STRATEGY_DETAIL = (strategyId: string) =>
  ['strategy-detail', strategyId] as const

export function useStrategyDetailQuery(strategyId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: QUERY_KEY_STRATEGY_DETAIL(strategyId),
    queryFn: async (): Promise<StrategyResponse> => {
      const response = await controlApi.getStrategyByIdApiV1StateStrategiesStrategyIdGet({
        strategyId,
      })
      return response.data
    },
    enabled: !!strategyId && (options?.enabled ?? true),
  })
}
