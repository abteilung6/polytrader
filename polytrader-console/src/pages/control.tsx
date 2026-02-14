/**
 * Control page — operator control plane for execution layers and health.
 *
 * Per PILOT_LIVE.md §5.1 / §5.3: Central page for:
 * - Toggling execution enabled/disabled (with typed confirmation)
 * - Activating/resetting kill switch (with typed confirmation)
 * - Viewing circuit breaker status
 * - Monitoring health gate statuses
 * - Viewing active live strategies
 */

import type { FC } from 'react'

import { ExecutionControlPanel } from '@/features/control/execution-control-panel'
import { HealthGatesPanel } from '@/features/control/health-gates-panel'
import { ActiveStrategiesPanel } from '@/features/control/active-strategies-panel'

export const ControlPage: FC = () => {
  return (
    <div className="flex flex-col gap-4 p-4">
      {/* Top row: Execution Controls + Health Gates side by side */}
      <div className="grid items-start gap-4 lg:grid-cols-2">
        <HealthGatesPanel />
        <ExecutionControlPanel />
      </div>
      {/* Full-width: Active Live Strategies */}
      <ActiveStrategiesPanel />
    </div>
  )
}
