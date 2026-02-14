/**
 * Hook for live (active) strategies polling.
 *
 * Per PILOT_LIVE.md §5.2: The operator needs to see which strategies
 * are activated for live trading. This feeds the live trading banner
 * (active count) and the control page's active strategies panel.
 *
 * Polls GET /api/v1/state/live-strategies every 3 seconds.
 */

import { useQuery } from '@tanstack/react-query'

import { controlApi } from '@/lib/api-client'
import type { LiveStrategiesResponse } from '@/lib/api'

export const QUERY_KEY_LIVE_STRATEGIES = ['live-strategies'] as const

/**
 * Poll active live strategy IDs.
 *
 * Returns list of strategy IDs that are currently activated for live trading.
 * Polling interval: 3s for near-real-time visibility.
 */
export function useLiveStrategiesQuery() {
  return useQuery({
    queryKey: QUERY_KEY_LIVE_STRATEGIES,
    queryFn: async (): Promise<LiveStrategiesResponse> => {
      const response = await controlApi.getLiveStrategiesApiV1StateLiveStrategiesGet()
      return response.data
    },
    refetchInterval: 3000,
  })
}
