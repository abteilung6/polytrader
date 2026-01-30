import type { FC } from 'react'
import { useParams } from '@tanstack/react-router'
import { useHistoricalTicksQuery } from '../hooks/historical-ticks'

export const MarketDetailPage: FC = () => {
  const { marketSlug } = useParams({ strict: false })
  const upTicks = useHistoricalTicksQuery(
    { marketSlug: marketSlug ?? '', outcome: 'UP' },
    { enabled: !!marketSlug },
  )
  const downTicks = useHistoricalTicksQuery(
    { marketSlug: marketSlug ?? '', outcome: 'DOWN' },
    { enabled: !!marketSlug },
  )

  if (!marketSlug) {
    return (
      <div className="flex min-h-svh flex-col bg-background p-4">
        <p className="text-muted-foreground">Market: —</p>
      </div>
    )
  }

  const loading = upTicks.isLoading || downTicks.isLoading
  const error = upTicks.error ?? downTicks.error

  if (loading) {
    return (
      <div className="flex min-h-svh flex-col bg-background p-4">
        <p className="text-muted-foreground">Market: {marketSlug}</p>
        <p className="text-muted-foreground">Loading ticks…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex min-h-svh flex-col bg-background p-4">
        <p className="text-muted-foreground">Market: {marketSlug}</p>
        <p className="text-destructive">Error loading ticks: {String(error)}</p>
      </div>
    )
  }

  return (
    <div className="flex min-h-svh flex-col gap-4 bg-background p-4">
      <p className="text-muted-foreground">Market: {marketSlug}</p>
      <section>
        <h2 className="mb-2 font-medium">UP ticks (raw JSON)</h2>
        <pre className="overflow-auto rounded border bg-muted p-3 text-sm">
          {JSON.stringify(upTicks.data ?? null, null, 2)}
        </pre>
      </section>
      <section>
        <h2 className="mb-2 font-medium">DOWN ticks (raw JSON)</h2>
        <pre className="overflow-auto rounded border bg-muted p-3 text-sm">
          {JSON.stringify(downTicks.data ?? null, null, 2)}
        </pre>
      </section>
    </div>
  )
}
