import { useQuery } from '@tanstack/react-query'

import { controlApi } from '@/lib/api-client'
import type { PerformanceOverviewResponse } from '@/lib/api'

export const QUERY_KEY_PERFORMANCE_OVERVIEW = 'performance-overview'

interface PerformanceOverviewParams {
  since?: string
  until?: string
}

export function usePerformanceOverviewQuery(params: PerformanceOverviewParams = {}) {
  return useQuery({
    queryKey: [QUERY_KEY_PERFORMANCE_OVERVIEW, params.since, params.until],
    queryFn: async (): Promise<PerformanceOverviewResponse> => {
      const response =
        await controlApi.getPerformanceOverviewApiV1StateStrategiesPerformanceOverviewGet({
          since: params.since ?? undefined,
          until: params.until ?? undefined,
        })
      return response.data
    },
  })
}
