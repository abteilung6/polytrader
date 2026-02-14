/**
 * Recent live orders table — execution_mode === 'live' only, last 50.
 *
 * Per PILOT_LIVE.md Commit 10: Columns Time | Strategy | Market | Side |
 * Size | State | Venue ID. Color-coded state badges (FILLED=green, REJECTED=red).
 */

import { useQueries } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'

import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useLiveStrategiesQuery } from '@/hooks/use-live-strategies'
import { useStrategyInstancesQuery } from '@/hooks/strategy-instances'
import { controlApi } from '@/lib/api-client'
import type { StrategyOrderItem } from '@/lib/api'

const PAGE_SIZE = 10

type LiveOrderRow = StrategyOrderItem & { strategy_id: string; strategy_name: string }

function formatTs(v: string): string {
  try {
    return new Date(v).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
  } catch {
    return '—'
  }
}

function orderStatusVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (status) {
    case 'FILLED':
      return 'default' // green when combined with className
    case 'REJECTED':
    case 'CANCELLED':
    case 'EXPIRED':
      return 'destructive'
    default:
      return 'secondary'
  }
}

export function LiveOrdersTable() {
  const { data: liveData, isLoading: liveLoading } = useLiveStrategiesQuery()
  const { data: instancesData, isLoading: instancesLoading } = useStrategyInstancesQuery()
  const activeIds = liveData?.active_strategies ?? []
  const strategyIdsToFetch = activeIds.slice(0, 20)
  const strategies = instancesData?.strategies ?? []
  const nameById = Object.fromEntries(strategies.map((s) => [s.strategy_id, s.name]))

  const orderQueries = useQueries({
    queries: strategyIdsToFetch.map((strategyId) => ({
      queryKey: ['strategy-orders', strategyId, 100],
      queryFn: async () => {
        const res = await controlApi.getStrategyOrdersApiV1StateStrategiesStrategyIdOrdersGet({
          strategyId,
          limit: 100,
        })
        return res.data
      },
      enabled: activeIds.length > 0,
    })),
  })

  const ordersLoading = orderQueries.some((q) => q.isPending)
  const isLoading = liveLoading || instancesLoading || ordersLoading

  const liveOrdersWithStrategy: LiveOrderRow[] = orderQueries
    .flatMap((q, i) => {
      const strategyId = strategyIdsToFetch[i]
      if (!strategyId || !q.data?.items) return []
      return q.data.items
        .filter((o) => o.execution_mode === 'live')
        .map((o) => ({
          ...o,
          strategy_id: strategyId,
          strategy_name: nameById[strategyId] ?? strategyId,
        }))
    })
    .sort((a, b) => new Date(b.ts_wall).getTime() - new Date(a.ts_wall).getTime())
    .slice(0, PAGE_SIZE)

  return (
    <div className="flex flex-col gap-4" data-testid="live-orders-table">
      {isLoading && (
        <div className="space-y-2" data-testid="live-orders-loading">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      )}

      {!isLoading && liveOrdersWithStrategy.length === 0 && (
        <p
          className="text-muted-foreground py-8 text-center text-sm"
          data-testid="live-orders-empty"
        >
          No live orders yet
        </p>
      )}

      {!isLoading && liveOrdersWithStrategy.length > 0 && (
        <div className="overflow-hidden rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Strategy</TableHead>
                <TableHead>Market</TableHead>
                <TableHead>Side</TableHead>
                <TableHead className="text-right">Size</TableHead>
                <TableHead>State</TableHead>
                <TableHead>Venue ID</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {liveOrdersWithStrategy.map((order) => (
                <TableRow key={order.order_id} data-testid={`live-order-row-${order.order_id}`}>
                  <TableCell className="tabular-nums text-muted-foreground text-sm">
                    {formatTs(order.ts_wall)}
                  </TableCell>
                  <TableCell>
                    <Link
                      to="/strategies/instances/$strategyId"
                      params={{ strategyId: order.strategy_id }}
                      className="font-medium hover:underline"
                    >
                      {order.strategy_name}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <Link
                      to="/markets/$marketSlug"
                      params={{ marketSlug: order.market_slug }}
                      className="hover:underline"
                    >
                      {order.market_slug}
                    </Link>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{order.side}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {Number(order.size).toFixed(2)}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={orderStatusVariant(order.status)}
                      className={
                        order.status === 'FILLED'
                          ? 'bg-green-600 text-white hover:bg-green-600'
                          : undefined
                      }
                    >
                      {order.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-mono text-muted-foreground text-xs">
                    {order.client_order_id}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
