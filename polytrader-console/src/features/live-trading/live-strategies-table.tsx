/**
 * Live strategies table — only live-activated AND running strategies.
 * Page size 10, no card wrapper.
 */

import { useState } from 'react'
import { Link } from '@tanstack/react-router'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
import type { StrategyResponse } from '@/lib/api'

const PAGE_SIZE = 10

export function LiveStrategiesTable() {
  const { data: liveData, isLoading: liveLoading } = useLiveStrategiesQuery()
  const { data: instancesData, isLoading: instancesLoading } = useStrategyInstancesQuery()
  const [page, setPage] = useState(0)

  const activeIds = new Set(liveData?.active_strategies ?? [])
  const strategies = instancesData?.strategies ?? []

  const liveRunning = strategies.filter(
    (s) => activeIds.has(s.strategy_id) && s.actual_state === 'RUNNING',
  )
  const totalPages = Math.max(1, Math.ceil(liveRunning.length / PAGE_SIZE))
  const paged = liveRunning.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const isLoading = liveLoading || instancesLoading

  return (
    <div className="flex flex-col gap-4" data-testid="live-strategies-table">
      {isLoading && (
        <div className="space-y-2" data-testid="live-strategies-loading">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      )}

      {!isLoading && liveRunning.length === 0 && (
        <p
          className="text-muted-foreground py-8 text-center text-sm"
          data-testid="live-strategies-empty"
        >
          No strategies currently trading live
        </p>
      )}

      {!isLoading && liveRunning.length > 0 && (
        <>
          <div className="overflow-hidden rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Template</TableHead>
                  <TableHead>Market</TableHead>
                  <TableHead>State</TableHead>
                  <TableHead>Mode</TableHead>
                  <TableHead>Last Signal</TableHead>
                  <TableHead className="w-[80px]">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paged.map((strategy) => (
                  <LiveStrategyRow key={strategy.strategy_id} strategy={strategy} />
                ))}
              </TableBody>
            </Table>
          </div>
          {totalPages > 1 && (
            <div
              className="flex items-center justify-between"
              data-testid="live-strategies-pagination"
            >
              <p className="text-muted-foreground text-sm">
                Page {page + 1} of {totalPages} ({liveRunning.length} total)
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page === 0}
                  onClick={() => setPage((p) => p - 1)}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages - 1}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function LiveStrategyRow({ strategy }: { strategy: StrategyResponse }) {
  return (
    <TableRow data-testid={`live-strategy-row-${strategy.strategy_id}`}>
      <TableCell>
        <Link
          to="/strategies/instances/$strategyId"
          params={{ strategyId: strategy.strategy_id }}
          className="font-medium hover:underline"
        >
          {strategy.name}
        </Link>
      </TableCell>
      <TableCell className="text-muted-foreground text-sm">
        {strategy.template_type_id} v{strategy.template_version}
      </TableCell>
      <TableCell className="text-muted-foreground text-sm">—</TableCell>
      <TableCell>
        <Badge variant="secondary">{strategy.actual_state}</Badge>
      </TableCell>
      <TableCell>
        <Badge variant="destructive">LIVE</Badge>
      </TableCell>
      <TableCell className="text-muted-foreground text-sm">—</TableCell>
      <TableCell>
        <Link
          to="/strategies/instances/$strategyId"
          params={{ strategyId: strategy.strategy_id }}
          className="text-primary text-sm hover:underline"
        >
          View
        </Link>
      </TableCell>
    </TableRow>
  )
}
