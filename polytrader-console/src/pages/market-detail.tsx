import type { FC } from 'react'
import { useParams } from '@tanstack/react-router'
import { Line, LineChart, XAxis } from 'recharts'
import { useHistoricalTicksQuery } from '../hooks/historical-ticks'
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '../components/ui/chart'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import type { HistoricalTicksResponse } from '../lib/api'

const chartConfig = {
  up: {
    label: 'UP',
    color: 'var(--chart-1)',
  },
  down: {
    label: 'DOWN',
    color: 'var(--chart-2)',
  },
} satisfies ChartConfig

type ChartDatum = { ts: string; up: number | undefined; down: number | undefined }

function buildChartData(
  upResponse: HistoricalTicksResponse | undefined,
  downResponse: HistoricalTicksResponse | undefined,
): ChartDatum[] {
  if (!upResponse?.ticks?.length && !downResponse?.ticks?.length) return []
  const upByTs = new Map((upResponse?.ticks ?? []).map((t) => [t.ts_wall, Number(t.mid)]))
  const downByTs = new Map((downResponse?.ticks ?? []).map((t) => [t.ts_wall, Number(t.mid)]))
  const allTs = [...new Set([...upByTs.keys(), ...downByTs.keys()])].sort()
  return allTs.map((ts) => ({
    ts,
    up: upByTs.get(ts),
    down: downByTs.get(ts),
  }))
}

/** Format as "05:18 PM" / "05:18 AM". */
function formatTsShort(ts: string): string {
  try {
    const d = new Date(ts)
    const h = d.getHours()
    const m = d.getMinutes()
    const hour12 = h % 12 || 12
    const pad = (n: number) => n.toString().padStart(2, '0')
    const period = h < 12 ? 'AM' : 'PM'
    return `${pad(hour12)}:${pad(m)} ${period}`
  } catch {
    return ts.slice(0, 19)
  }
}

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

  const chartData = buildChartData(upTicks.data, downTicks.data)

  return (
    <div className="flex min-h-svh flex-col gap-4 bg-background p-4">
      <Card className="py-4 sm:py-0">
        <CardHeader className="flex flex-col items-stretch border-b !p-0 sm:flex-row">
          <div className="flex flex-1 flex-col justify-center gap-1 p-6">
            <CardTitle className="text-lg font-semibold leading-none tracking-tight">
              {marketSlug}
            </CardTitle>
            <CardDescription>Historical ticks mid price over time (UTC)</CardDescription>
          </div>
        </CardHeader>
        <CardContent className="px-2 sm:p-6">
          <ChartContainer config={chartConfig} className="aspect-auto h-[250px] w-full">
            <LineChart accessibilityLayer data={chartData} margin={{ left: 12, right: 12 }}>
              <XAxis
                dataKey="ts"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                minTickGap={32}
                tickFormatter={formatTsShort}
                tick={{ style: { fontSize: '0.65rem' } }}
              />
              <ChartTooltip
                cursor={false}
                content={({ active, payload, label }) => (
                  <ChartTooltipContent
                    active={active}
                    payload={
                      payload as
                        | { name?: string; value?: number; dataKey?: string; color?: string }[]
                        | undefined
                    }
                    label={label != null ? formatTsShort(String(label)) : undefined}
                  />
                )}
              />
              <Line
                dataKey="up"
                type="monotone"
                stroke="var(--color-up)"
                strokeWidth={2}
                dot={false}
                connectNulls
              />
              <Line
                dataKey="down"
                type="monotone"
                stroke="var(--color-down)"
                strokeWidth={2}
                dot={false}
                connectNulls
              />
            </LineChart>
          </ChartContainer>
        </CardContent>
      </Card>
    </div>
  )
}
