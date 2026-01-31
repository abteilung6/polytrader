import type { FC } from 'react'
import { Link, useParams } from '@tanstack/react-router'

import { StrategySignalsDataTable } from '@/components/strategies/strategy-signals-data-table'
import { strategySignalColumns } from '@/components/strategies/signal-columns'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useStrategyDetailQuery } from '@/hooks/strategy-detail'
import { useStrategySignalsQuery } from '@/hooks/strategy-signals'

export const StrategyInstanceDetailPage: FC = () => {
  const { strategyId } = useParams({ strict: false })
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

  return (
    <Tabs defaultValue="signals" className="w-full flex-col gap-4">
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
        <p className="text-muted-foreground">Orders table placeholder.</p>
      </TabsContent>
    </Tabs>
  )
}
