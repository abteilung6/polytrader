import { useQuery } from '@tanstack/react-query'
import { marketApi } from '../lib/api-client'
import type { MarketsResponse } from '../lib/api'
import type { MarketApiGetMarketsApiV1MarketMarketsGetRequest } from '../lib/api/services/market-api'

export const QUERY_KEY_MARKETS = ['markets'] as const

export const useMarketsQuery = (request?: MarketApiGetMarketsApiV1MarketMarketsGetRequest) =>
  useQuery({
    queryKey: [...QUERY_KEY_MARKETS, request],
    queryFn: async (): Promise<MarketsResponse> => {
      const response = await marketApi.getMarketsApiV1MarketMarketsGet(request ?? {})
      return response.data
    },
  })
