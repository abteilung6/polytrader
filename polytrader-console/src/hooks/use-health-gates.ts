/**
 * Hook for health gates polling.
 *
 * Per PILOT_LIVE.md §5.1: Pre-session system health check.
 * The control page displays health gates so the operator can verify
 * the system is healthy before enabling execution.
 *
 * Polls GET /api/v1/state/health every 5 seconds.
 */

import { useQuery } from '@tanstack/react-query'

import { controlApi } from '@/lib/api-client'
import type { HealthResponse } from '@/lib/api'

export const QUERY_KEY_HEALTH_GATES = ['health-gates'] as const

/**
 * Poll system health gates.
 *
 * Returns overall status (ok/degraded/down) and individual gate statuses
 * (db, market_data_freshness, event_bus_lag, venue_connectivity, risk_engine).
 */
export function useHealthGatesQuery() {
  return useQuery({
    queryKey: QUERY_KEY_HEALTH_GATES,
    queryFn: async (): Promise<HealthResponse> => {
      const response = await controlApi.getHealthApiV1StateHealthGet()
      return response.data
    },
    refetchInterval: 5000,
  })
}
