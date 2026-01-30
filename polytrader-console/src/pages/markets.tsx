import type { FC } from 'react'

import { MarketsDataTable } from '@/components/markets/markets-data-table'
import { marketColumns } from '@/components/markets/columns'
import { useMarketsQuery } from '@/hooks/markets'

export const MarketsPage: FC = () => {
  const { data, isPending, error } = useMarketsQuery({
    pattern: 'btc-updown-15m',
  })

  if (isPending) {
    return (
      <div className="flex min-h-svh flex-col items-center justify-center bg-background">
        <p className="text-muted-foreground">Loading…</p>
      </div>
    )
  }
  if (error) {
    return (
      <div className="flex min-h-svh flex-col items-center justify-center bg-background p-4">
        <p className="text-destructive">
          Error: {error instanceof Error ? error.message : String(error)}
        </p>
      </div>
    )
  }
  if (!data) return null

  const markets = data.markets ?? []

  return <MarketsDataTable columns={marketColumns} data={markets} />
}
