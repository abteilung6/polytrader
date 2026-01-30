import type { FC } from 'react'
import { useParams } from '@tanstack/react-router'
import { Line, LineChart, XAxis } from 'recharts'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart'
import { useHistoricalTicksQuery } from '@/hooks/historical-ticks'
import { useMarketsQuery } from '@/hooks/markets'
import type { HistoricalTicksResponse } from '@/lib/api'

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

type ChartDatum = { ts: string; tsMs: number; up: number | undefined; down: number | undefined }

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
    tsMs: new Date(ts).getTime(),
    up: upByTs.get(ts),
    down: downByTs.get(ts),
  }))
}

/** Format as "05:18 PM" / "05:18 AM". */
function formatTsShort(ts: string): string
function formatTsShort(tsMs: number): string
function formatTsShort(tsOrMs: string | number): string {
  try {
    const d = typeof tsOrMs === 'number' ? new Date(tsOrMs) : new Date(tsOrMs)
    const h = d.getHours()
    const m = d.getMinutes()
    const hour12 = h % 12 || 12
    const pad = (n: number) => n.toString().padStart(2, '0')
    const period = h < 12 ? 'AM' : 'PM'
    return `${pad(hour12)}:${pad(m)} ${period}`
  } catch {
    return typeof tsOrMs === 'string' ? tsOrMs.slice(0, 19) : '—'
  }
}

/** Derive pattern from slug (e.g. "btc-updown-15m-1769789700" -> "btc-updown-15m"). */
function patternFromSlug(slug: string): string {
  const parts = slug.split('-')
  if (parts.length < 2) return slug
  return parts.slice(0, -1).join('-')
}

export const MarketDetailPage: FC = () => {
  const { marketSlug } = useParams({ strict: false })
  const pattern = marketSlug ? patternFromSlug(marketSlug) : ''
  const marketsQuery = useMarketsQuery({ pattern: pattern || undefined })
  const market = marketSlug
    ? marketsQuery.data?.markets?.find((m) => m.market_slug === marketSlug)
    : undefined
  const startMs = market?.start_date ? new Date(market.start_date).getTime() : undefined
  const endMs = market?.end_date ? new Date(market.end_date).getTime() : undefined

  const upTicks = useHistoricalTicksQuery(
    { marketSlug: marketSlug ?? '', outcome: 'UP' },
    { enabled: !!marketSlug },
  )
  const downTicks = useHistoricalTicksQuery(
    { marketSlug: marketSlug ?? '', outcome: 'DOWN' },
    { enabled: !!marketSlug },
  )

  if (!marketSlug) {
    return <p className="text-muted-foreground">Market: —</p>
  }

  const loading = upTicks.isLoading || downTicks.isLoading
  const error = upTicks.error ?? downTicks.error

  if (loading) {
    return (
      <>
        <p className="text-muted-foreground">Market: {marketSlug}</p>
        <p className="text-muted-foreground">Loading ticks…</p>
      </>
    )
  }

  if (error) {
    return (
      <>
        <p className="text-muted-foreground">Market: {marketSlug}</p>
        <p className="text-destructive">Error loading ticks: {String(error)}</p>
      </>
    )
  }

  const chartData = buildChartData(upTicks.data, downTicks.data)

  return (
    <div className="flex flex-col gap-2">
      <Card className="py-2 sm:py-0">
        <CardHeader className="flex flex-col items-stretch border-b !p-0 sm:flex-row">
          <div className="flex flex-1 flex-col justify-center gap-1 p-4">
            <CardTitle className="text-lg font-semibold leading-none tracking-tight">
              {marketSlug}
            </CardTitle>
            <CardDescription>Historical ticks mid price over time (UTC)</CardDescription>
          </div>
        </CardHeader>
        <CardContent className="px-0 sm:px-2">
          <ChartContainer config={chartConfig} className="aspect-auto h-[250px] w-full">
            <LineChart accessibilityLayer data={chartData} margin={{ left: 4, right: 4 }}>
              <XAxis
                dataKey="tsMs"
                type="number"
                domain={startMs != null && endMs != null ? [startMs, endMs] : undefined}
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                minTickGap={20}
                tickCount={12}
                tickFormatter={(val: number) => formatTsShort(val)}
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
                    label={
                      label != null
                        ? formatTsShort(typeof label === 'number' ? label : Number(label))
                        : undefined
                    }
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
