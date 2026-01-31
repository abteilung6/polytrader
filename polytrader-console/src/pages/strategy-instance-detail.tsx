import type { FC } from 'react'
import { Link, useNavigate, useParams, useSearch } from '@tanstack/react-router'

import { StrategyOrdersDataTable } from '@/components/strategies/strategy-orders-data-table'
import { strategyOrderColumns } from '@/components/strategies/order-columns'
import { StrategySignalsDataTable } from '@/components/strategies/strategy-signals-data-table'
import { strategySignalColumns } from '@/components/strategies/signal-columns'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useStrategyDetailQuery } from '@/hooks/strategy-detail'
import { useStrategyOrdersQuery } from '@/hooks/strategy-orders'
import { useStrategySignalsQuery } from '@/hooks/strategy-signals'

export const StrategyInstanceDetailPage: FC = () => {
  const { strategyId } = useParams({ strict: false })
  const { tab: tabParam } = useSearch({ strict: false })
  const navigate = useNavigate()
  const activeTab = tabParam === 'orders' ? 'orders' : 'signals'
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
    void navigate({
      to: '/strategies/instances/$strategyId',
      params: { strategyId },
      search: value === 'orders' ? { tab: 'orders' } : { tab: 'signals' },
    })
  }

  return (
    <Tabs value={activeTab} onValueChange={setTab} className="w-full flex-col gap-4">
      <TabsList>
        <TabsTrigger value="signals">Signals</TabsTrigger>
        <TabsTrigger value="orders">Orders</TabsTrigger>
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
          <StrategyOrdersDataTable columns={strategyOrderColumns} data={ordersData?.items ?? []} />
        )}
      </TabsContent>
    </Tabs>
  )
}
