/**
 * Hooks for execution state queries and mutations.
 *
 * Per PILOT_LIVE.md §5.1 / §5.3: The execution state is the primary
 * operational control — it determines whether real orders can be placed.
 *
 * Query polling frequency adapts to execution state:
 * - 2s when execution enabled (higher vigilance during live trading)
 * - 5s when execution disabled (lower cost during paper mode)
 *
 * Mutations:
 * - Enable/Disable execution (queued commands)
 * - Kill switch activate/reset (direct-apply, immediate)
 *
 * All mutations invalidate the execution state query on success.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { controlApi } from '@/lib/api-client'
import type { ExecutionStateResponse } from '@/lib/api'

export const QUERY_KEY_EXECUTION_STATE = ['execution-state'] as const

/**
 * Poll execution state with adaptive interval.
 *
 * Returns execution_enabled, kill_switch_active, version, updated_at, etc.
 * Polling interval: 2s when execution enabled, 5s otherwise.
 */
export function useExecutionStateQuery() {
  return useQuery({
    queryKey: QUERY_KEY_EXECUTION_STATE,
    queryFn: async (): Promise<ExecutionStateResponse> => {
      const response = await controlApi.getExecutionStateApiV1StateExecutionGet()
      return response.data
    },
    refetchInterval: (query) => {
      const data = query.state.data
      return data?.execution_enabled ? 2000 : 5000
    },
  })
}

/**
 * Enable execution (queued command).
 *
 * Per flows.mdc §2: Execution requires explicit enabling after health gates pass.
 * This is a queued command — the control plane processes it asynchronously.
 */
export function useEnableExecutionMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (params: { reason: string }) => {
      const response = await controlApi.enableExecutionApiV1CommandsExecutionEnablePost({
        enableExecutionRequest: {
          reason: params.reason,
          issued_by: 'operator',
          client_request_id: `enable-exec-${Date.now()}`,
        },
      })
      return response.data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY_EXECUTION_STATE })
    },
  })
}

/**
 * Disable execution (queued command).
 *
 * Per flows.mdc §13: Disabling execution prevents new orders from being placed.
 * Existing open orders are NOT automatically cancelled (use kill switch for that).
 */
export function useDisableExecutionMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (params: { reason: string }) => {
      const response = await controlApi.disableExecutionApiV1CommandsExecutionDisablePost({
        disableExecutionRequest: {
          reason: params.reason,
          issued_by: 'operator',
          client_request_id: `disable-exec-${Date.now()}`,
        },
      })
      return response.data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY_EXECUTION_STATE })
    },
  })
}

/**
 * Activate kill switch (direct-apply, immediate).
 *
 * Per PILOT_LIVE.md §3.2.5: Kill switch is immediate — not queued.
 * It disables execution, sets kill_switch_active, and optionally cancels
 * all open orders. This is a safety-critical action.
 */
export function useKillSwitchMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (params: { reason: string; cancelOpenOrders?: boolean }) => {
      const response = await controlApi.activateKillSwitchApiV1CommandsExecutionKillSwitchPost({
        killSwitchRequest: {
          reason: params.reason,
          cancel_open_orders: params.cancelOpenOrders ?? true,
          issued_by: 'operator',
        },
      })
      return response.data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY_EXECUTION_STATE })
    },
  })
}

/**
 * Reset (deactivate) kill switch (direct-apply, immediate).
 *
 * Per PILOT_LIVE.md §3.2.5: Resetting the kill switch does NOT re-enable
 * execution. The operator must explicitly re-enable execution separately.
 * This is a safety measure to prevent accidental re-enablement.
 */
export function useKillSwitchResetMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (params: { reason: string }) => {
      const response = await controlApi.resetKillSwitchApiV1CommandsExecutionKillSwitchResetPost({
        killSwitchResetRequest: {
          reason: params.reason,
          issued_by: 'operator',
        },
      })
      return response.data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY_EXECUTION_STATE })
    },
  })
}
