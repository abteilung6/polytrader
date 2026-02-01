import type { FC } from 'react'
import { Link, useNavigate, useParams, useSearch } from '@tanstack/react-router'

import { StrategyOrdersDataTable } from '@/components/strategies/strategy-orders-data-table'
import { strategyOrderColumns } from '@/components/strategies/order-columns'
import { StrategyPerformanceDataTable } from '@/components/strategies/strategy-performance-data-table'
import { strategyPerformanceColumns } from '@/components/strategies/performance-columns'
import { PerformanceSummaryCards } from '@/components/strategies/performance-summary-cards'
import { StrategySignalsDataTable } from '@/components/strategies/strategy-signals-data-table'
import { strategySignalColumns } from '@/components/strategies/signal-columns'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useStrategyDetailQuery } from '@/hooks/strategy-detail'
import {
  useStrategyPerformanceQuery,
  flattenPerformanceItems,
  firstPageSummary,
} from '@/hooks/strategy-performance'
import { useStrategyOrdersQuery } from '@/hooks/strategy-orders'
import { useStrategySignalsQuery } from '@/hooks/strategy-signals'

type TabValue = 'signals' | 'orders' | 'performance'

export const StrategyInstanceDetailPage: FC = () => {
  const { strategyId } = useParams({ strict: false })
  const { tab: tabParam } = useSearch({ strict: false })
  const navigate = useNavigate()
  const activeTab: TabValue =
    tabParam === 'performance' ? 'performance' : tabParam === 'orders' ? 'orders' : 'signals'
  const { data, isPending, error, isError, fetchStatus } = useStrategyDetailQuery(
    strategyId ?? '',
    { enabled: !!strategyId },
  )
  const {
    data: signalsData,
    isPending: signalsPending,
    error: signalsError,
    isError: signalsIsError,
  } = useStrategySignalsQuery(strategyId ?? '', { enabled: !!strategyId && !!data })
  const {
    data: ordersData,
    isPending: ordersPending,
    error: ordersError,
    isError: ordersIsError,
  } = useStrategyOrdersQuery(strategyId ?? '', { enabled: !!strategyId && !!data })
  const {
    data: performanceData,
    isPending: performancePending,
    error: performanceError,
    isError: performanceIsError,
    hasNextPage: performanceHasNextPage,
    isFetchingNextPage: performanceFetchingNextPage,
    fetchNextPage: performanceFetchNextPage,
  } = useStrategyPerformanceQuery(strategyId ?? '', {
    enabled: !!strategyId && !!data,
  })
  const performanceItems = flattenPerformanceItems(performanceData?.pages)
  const performanceSummary = firstPageSummary(performanceData?.pages)

  if (!strategyId) {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-muted-foreground">Missing strategy ID.</p>
        <Link to="/strategies/instances" className="text-primary underline">
          ← Strategy instances
        </Link>
      </div>
    )
  }

  if (isPending && fetchStatus !== 'idle') {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-muted-foreground">Loading…</p>
      </div>
    )
  }

  if (isError && error) {
    const status = (error as { response?: { status?: number } })?.response?.status
    if (status === 404) {
      return (
        <div className="flex flex-col gap-2">
          <p className="text-muted-foreground">Strategy not found.</p>
          <Link to="/strategies/instances" className="text-primary underline">
            ← Strategy instances
          </Link>
        </div>
      )
    }
    return (
      <div className="flex flex-col gap-2">
        <p className="text-destructive">
          Error: {error instanceof Error ? error.message : String(error)}
        </p>
        <Link to="/strategies/instances" className="text-primary underline">
          ← Strategy instances
        </Link>
      </div>
    )
  }

  if (!data) return null

  const setTab = (value: string) => {
    const tab: TabValue =
      value === 'performance' ? 'performance' : value === 'orders' ? 'orders' : 'signals'
    void navigate({
      to: '/strategies/instances/$strategyId',
      params: { strategyId },
      search: { tab },
    })
  }

  return (
    <div className="flex w-full flex-col gap-4 py-4 md:gap-6 md:py-6">
      <PerformanceSummaryCards summary={performanceSummary} isPending={performancePending} />
      <Tabs value={activeTab} onValueChange={setTab} className="w-full flex-col gap-4">
        <TabsList>
          <TabsTrigger value="signals">Signals</TabsTrigger>
          <TabsTrigger value="orders">Orders</TabsTrigger>
          <TabsTrigger value="performance">Past Performance</TabsTrigger>
        </TabsList>
        <TabsContent value="signals" className="flex flex-col gap-4">
          {signalsPending ? (
            <p className="text-muted-foreground">Loading signals…</p>
          ) : signalsIsError && signalsError ? (
            <p className="text-destructive">
              Error: {signalsError instanceof Error ? signalsError.message : String(signalsError)}
            </p>
          ) : (
            <StrategySignalsDataTable
              columns={strategySignalColumns}
              data={signalsData?.items ?? []}
            />
          )}
        </TabsContent>
        <TabsContent value="orders" className="flex flex-col gap-4">
          {ordersPending ? (
            <p className="text-muted-foreground">Loading orders…</p>
          ) : ordersIsError && ordersError ? (
            <p className="text-destructive">
              Error: {ordersError instanceof Error ? ordersError.message : String(ordersError)}
            </p>
          ) : (
            <StrategyOrdersDataTable
              columns={strategyOrderColumns}
              data={ordersData?.items ?? []}
            />
          )}
        </TabsContent>
        <TabsContent value="performance" className="flex flex-col gap-4">
          {performancePending ? (
            <p className="text-muted-foreground">Loading performance…</p>
          ) : performanceIsError && performanceError ? (
            <p className="text-destructive">
              Error:{' '}
              {performanceError instanceof Error
                ? performanceError.message
                : String(performanceError)}
            </p>
          ) : (
            <StrategyPerformanceDataTable
              columns={strategyPerformanceColumns}
              data={performanceItems}
              hasNextPage={performanceHasNextPage}
              isFetchingNextPage={performanceFetchingNextPage}
              onLoadMore={() => void performanceFetchNextPage()}
            />
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
