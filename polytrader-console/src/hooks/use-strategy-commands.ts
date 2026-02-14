/**
 * Hooks for strategy lifecycle commands (start/stop).
 *
 * Per PILOT_LIVE.md §5.2: Strategy lifecycle controls allow the operator
 * to start and stop strategy instances. These use the PATCH endpoint
 * to update the desired_state.
 *
 * Per flows.mdc §2: Strategy lifecycle is a state machine:
 *   STOPPED → STARTING → RUNNING → PAUSED → DRAINING → STOPPING → STOPPED
 *
 * Start: sets desired_state = "RUNNING"
 * Stop:  sets desired_state = "STOPPED"
 *
 * Both mutations invalidate the strategy instances query on success.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'

import { controlApi } from '@/lib/api-client'
import { QUERY_KEY_STRATEGY_INSTANCES } from '@/hooks/strategy-instances'

/**
 * Start a strategy instance (set desired_state = RUNNING).
 *
 * Per PILOT_LIVE.md: Start is considered a safe action — no confirmation
 * dialog required. The strategy will begin signal generation.
 */
export function useStartStrategyMutation(strategyId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      const response = await controlApi.updateStrategyApiV1CommandsStrategiesStrategyIdPatch({
        strategyId,
        updateStrategyRequest: {
          desired_state: 'RUNNING',
        },
      })
      return response.data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY_STRATEGY_INSTANCES })
    },
  })
}

/**
 * Stop a strategy instance (set desired_state = STOPPED).
 *
 * Per PILOT_LIVE.md §8.5: Stop should show a standard AlertDialog
 * confirmation ("Stop strategy? This will halt signal generation.").
 */
export function useStopStrategyMutation(strategyId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      const response = await controlApi.updateStrategyApiV1CommandsStrategiesStrategyIdPatch({
        strategyId,
        updateStrategyRequest: {
          desired_state: 'STOPPED',
        },
      })
      return response.data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY_STRATEGY_INSTANCES })
    },
  })
}
