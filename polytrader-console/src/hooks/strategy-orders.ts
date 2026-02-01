import { useQuery } from '@tanstack/react-query'

import { controlApi } from '@/lib/api-client'
import type { StrategyOrdersResponse } from '@/lib/api'

export const QUERY_KEY_STRATEGY_ORDERS = (strategyId: string) =>
  ['strategy-orders', strategyId] as const

const DEFAULT_LIMIT = 100

export function useStrategyOrdersQuery(
  strategyId: string,
  options?: { enabled?: boolean; limit?: number },
) {
  return useQuery({
    queryKey: [...QUERY_KEY_STRATEGY_ORDERS(strategyId), options?.limit ?? DEFAULT_LIMIT],
    queryFn: async (): Promise<StrategyOrdersResponse> => {
      const response = await controlApi.getStrategyOrdersApiV1StateStrategiesStrategyIdOrdersGet({
        strategyId,
        limit: options?.limit ?? DEFAULT_LIMIT,
      })
      return response.data
    },
    enabled: !!strategyId && (options?.enabled ?? true),
  })
}
