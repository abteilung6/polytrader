import type { FC } from 'react'

import { StrategyTemplatesDataTable } from '@/components/strategies/strategy-templates-data-table'
import { strategyTemplateColumns } from '@/components/strategies/columns'
import { useStrategyTemplatesQuery } from '@/hooks/strategy-templates'

export const StrategiesTemplatesPage: FC = () => {
  const { data, isPending, error } = useStrategyTemplatesQuery()

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

  const templates = data.types ?? []

  return (
    <div className="flex flex-col gap-2">
      <StrategyTemplatesDataTable columns={strategyTemplateColumns} data={templates} />
    </div>
  )
}
