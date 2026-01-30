import type { FC } from 'react'

import { StrategyInstancesDataTable } from '@/components/strategies/strategy-instances-data-table'
import { strategyInstanceColumns } from '@/components/strategies/instance-columns'
import { useStrategyInstancesQuery } from '@/hooks/strategy-instances'

export const StrategiesInstancesPage: FC = () => {
  const { data, isPending, error } = useStrategyInstancesQuery()

  if (isPending) {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-muted-foreground">Loading…</p>
      </div>
    )
  }
  if (error) {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-destructive">
          Error: {error instanceof Error ? error.message : String(error)}
        </p>
      </div>
    )
  }
  if (!data) return null

  const instances = data.strategies ?? []

  return (
    <div className="flex flex-col gap-2">
      <StrategyInstancesDataTable columns={strategyInstanceColumns} data={instances} />
    </div>
  )
}
