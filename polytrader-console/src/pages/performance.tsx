import { useMemo, useState, type FC } from 'react'

import { performanceOverviewColumns } from '@/components/performance/overview-columns'
import { PerformanceOverviewDataTable } from '@/components/performance/overview-data-table'
import { WindowSelector } from '@/components/performance/window-selector'
import { usePerformanceOverviewQuery } from '@/hooks/performance-overview'
import { computeWindowRange, DEFAULT_WINDOW, type WindowPreset } from '@/lib/window-presets'

export const PerformancePage: FC = () => {
  const [window, setWindow] = useState<WindowPreset>(DEFAULT_WINDOW)

  // Memoize range so the query key is stable across re-renders.
  // Recomputes only when the window preset changes.
  const range = useMemo(() => computeWindowRange(window), [window])

  const { data, isPending, error } = usePerformanceOverviewQuery({
    since: range.since,
    until: range.until,
  })

  return (
    <div className="flex flex-col gap-4 p-4">
      <h1 className="text-2xl font-bold">Performance Overview</h1>
      <div className="flex items-center gap-4">
        <WindowSelector value={window} onChange={setWindow} />
        <span className="text-sm text-muted-foreground">
          {range.since ? `Since ${new Date(range.since).toLocaleString()}` : 'All time'}
        </span>
      </div>

      {isPending && <p className="text-muted-foreground">Loading…</p>}
      {error && (
        <p className="text-destructive">
          Error: {error instanceof Error ? error.message : String(error)}
        </p>
      )}
      {data && (
        <PerformanceOverviewDataTable
          columns={performanceOverviewColumns}
          data={data.items ?? []}
        />
      )}
    </div>
  )
}
