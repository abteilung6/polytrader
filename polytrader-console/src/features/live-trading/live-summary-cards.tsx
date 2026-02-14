/**
 * Live trading summary cards — at-a-glance counts for the Live Trading dashboard.
 *
 * Per PILOT_LIVE.md Commit 10: 4 cards — Active Strategies, Open Orders,
 * Live Positions, Total Live PnL. Uses shadcn Card with CardHeader/CardTitle/
 * CardDescription/CardFooter; color-coded trend where applicable.
 */

import { useQueries } from '@tanstack/react-query'

import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useLiveStrategiesQuery } from '@/hooks/use-live-strategies'
import { usePerformanceOverviewQuery } from '@/hooks/performance-overview'
import { controlApi } from '@/lib/api-client'
import type { StrategyOrderItem } from '@/lib/api'

const NON_TERMINAL_STATUSES = new Set(['PENDING_SUBMIT', 'LIVE', 'PARTIALLY_FILLED', 'SUBMITTING'])

function isOpenOrder(order: StrategyOrderItem): boolean {
  return NON_TERMINAL_STATUSES.has(order.status)
}

export function LiveSummaryCards() {
  const { data: liveData, isLoading: liveLoading } = useLiveStrategiesQuery()
  const { data: perfData, isLoading: perfLoading } = usePerformanceOverviewQuery({
    executionMode: 'live',
  })
  const activeIds = liveData?.active_strategies ?? []

  // Fetch orders for each active strategy (cap to avoid too many requests)
  const orderQueries = useQueries({
    queries: activeIds.slice(0, 20).map((strategyId) => ({
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
  const allOrders: StrategyOrderItem[] = orderQueries
    .filter((q) => q.data?.items)
    .flatMap((q) => q.data!.items)
  const liveOrders = allOrders.filter((o) => o.execution_mode === 'live')
  const openOrdersCount = liveOrders.filter(isOpenOrder).length

  const totalLivePnl =
    perfData?.items?.reduce((sum, item) => sum + (item.total_realized_pnl ?? 0), 0) ?? 0
  const isLoading = liveLoading || ordersLoading

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" data-testid="live-summary-cards">
      <Card data-testid="card-active-strategies">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Active Strategies</CardTitle>
        </CardHeader>
        <CardContent>
          {liveLoading ? (
            <Skeleton className="h-8 w-16" />
          ) : (
            <span className="text-2xl font-bold" data-testid="count-active-strategies">
              {activeIds.length}
            </span>
          )}
        </CardContent>
        <CardFooter>
          <CardDescription>Strategies activated for live trading</CardDescription>
        </CardFooter>
      </Card>

      <Card data-testid="card-open-orders">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Open Orders</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-8 w-16" />
          ) : (
            <span className="text-2xl font-bold" data-testid="count-open-orders">
              {openOrdersCount}
            </span>
          )}
        </CardContent>
        <CardFooter>
          <CardDescription>Live orders not yet filled or cancelled</CardDescription>
        </CardFooter>
      </Card>

      <Card data-testid="card-positions">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Live Positions</CardTitle>
        </CardHeader>
        <CardContent>
          <span className="text-2xl font-bold tabular-nums" data-testid="count-positions">
            —
          </span>
        </CardContent>
        <CardFooter>
          <CardDescription>Position count (when API available)</CardDescription>
        </CardFooter>
      </Card>

      <Card data-testid="card-total-pnl">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Total Live PnL</CardTitle>
        </CardHeader>
        <CardContent>
          {perfLoading ? (
            <Skeleton className="h-8 w-20" />
          ) : (
            <span
              className={`text-2xl font-bold tabular-nums ${totalLivePnl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}
              data-testid="total-live-pnl"
            >
              {totalLivePnl >= 0 ? '+' : ''}
              {totalLivePnl.toFixed(2)}
            </span>
          )}
        </CardContent>
        <CardFooter>
          <CardDescription>Realized PnL from live closed trades</CardDescription>
        </CardFooter>
      </Card>
    </div>
  )
}
