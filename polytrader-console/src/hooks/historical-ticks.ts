import { useQuery } from '@tanstack/react-query'
import { marketApi } from '../lib/api-client'
import type { HistoricalTicksResponse } from '../lib/api'
import type { MarketApiGetHistoricalTicksApiV1MarketTicksHistoryGetRequest } from '../lib/api/services/market-api'

export const QUERY_KEY_HISTORICAL_TICKS = ['market', 'ticks', 'history'] as const

export type UseHistoricalTicksQueryParams = {
  marketSlug: string
  outcome: string
  fromTs?: string | null
  toTs?: string | null
  limit?: number
}

export const useHistoricalTicksQuery = (
  params: UseHistoricalTicksQueryParams,
  options?: { enabled?: boolean },
) => {
  const { marketSlug, outcome, fromTs, toTs, limit } = params
  const request: MarketApiGetHistoricalTicksApiV1MarketTicksHistoryGetRequest = {
    marketSlug,
    outcome,
    fromTs: fromTs ?? undefined,
    toTs: toTs ?? undefined,
    limit,
  }
  return useQuery({
    queryKey: [...QUERY_KEY_HISTORICAL_TICKS, request],
    queryFn: async (): Promise<HistoricalTicksResponse> => {
      const response = await marketApi.getHistoricalTicksApiV1MarketTicksHistoryGet(request)
      return response.data
    },
    enabled: options?.enabled !== false && !!marketSlug && !!outcome,
  })
}
