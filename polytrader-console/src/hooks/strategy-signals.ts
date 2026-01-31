import { useQuery } from '@tanstack/react-query'

import { controlApi } from '@/lib/api-client'
import type { StrategySignalsResponse } from '@/lib/api'

export const QUERY_KEY_STRATEGY_SIGNALS = (strategyId: string) =>
  ['strategy-signals', strategyId] as const

const DEFAULT_LIMIT = 100

export function useStrategySignalsQuery(
  strategyId: string,
  options?: { enabled?: boolean; limit?: number },
) {
  return useQuery({
    queryKey: [...QUERY_KEY_STRATEGY_SIGNALS(strategyId), options?.limit ?? DEFAULT_LIMIT],
    queryFn: async (): Promise<StrategySignalsResponse> => {
      const response = await controlApi.getStrategySignalsApiV1StateStrategiesStrategyIdSignalsGet({
        strategyId,
        limit: options?.limit ?? DEFAULT_LIMIT,
      })
      return response.data
    },
    enabled: !!strategyId && (options?.enabled ?? true),
  })
}
