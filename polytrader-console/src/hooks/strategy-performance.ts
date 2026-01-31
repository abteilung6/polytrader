import { useInfiniteQuery } from '@tanstack/react-query'

import { controlApi } from '@/lib/api-client'
import type { ClosedTradeItem, PerformanceResponse } from '@/lib/api'

export const QUERY_KEY_STRATEGY_PERFORMANCE = (strategyId: string) =>
  ['strategy-performance', strategyId] as const

const DEFAULT_LIMIT = 50

export function useStrategyPerformanceQuery(
  strategyId: string,
  options?: { enabled?: boolean; limit?: number },
) {
  return useInfiniteQuery({
    queryKey: [...QUERY_KEY_STRATEGY_PERFORMANCE(strategyId), options?.limit ?? DEFAULT_LIMIT],
    queryFn: async ({ pageParam }: { pageParam?: string | null }): Promise<PerformanceResponse> => {
      const response =
        await controlApi.getStrategyPerformanceApiV1StateStrategiesStrategyIdPerformanceGet({
          strategyId,
          limit: options?.limit ?? DEFAULT_LIMIT,
          cursor: pageParam ?? undefined,
        })
      return response.data
    },
    initialPageParam: undefined as string | null | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !!strategyId && (options?.enabled ?? true),
  })
}

/** Flatten all loaded pages into a single list of closed trades. */
export function flattenPerformanceItems(
  pages: PerformanceResponse[] | undefined,
): ClosedTradeItem[] {
  if (!pages?.length) return []
  return pages.flatMap((p) => p.items ?? [])
}

/** Summary from the first page (page-scoped summary from API). */
export function firstPageSummary(
  pages: PerformanceResponse[] | undefined,
): PerformanceResponse['summary'] | undefined {
  return pages?.[0]?.summary
}
