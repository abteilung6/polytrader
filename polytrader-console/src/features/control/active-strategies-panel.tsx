/**
 * Active strategies panel — lists strategies activated for live trading.
 *
 * Per PILOT_LIVE.md §5.2: The operator needs to see which strategies
 * are live-activated. Cross-references live strategy IDs with the
 * strategy instances list for full details.
 *
 * Paginated: max 10 rows per page.
 */

import { useState } from 'react'
import { Link } from '@tanstack/react-router'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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

const PAGE_SIZE = 5

export function ActiveStrategiesPanel() {
  const { data: liveData, isLoading: liveLoading } = useLiveStrategiesQuery()
  const { data: instancesData, isLoading: instancesLoading } = useStrategyInstancesQuery()
  const [page, setPage] = useState(0)

  const isLoading = liveLoading || instancesLoading
  const activeIds = liveData?.active_strategies ?? []
  const strategies = instancesData?.strategies ?? []

  // Match live strategy IDs to full strategy details
  const activeStrategies = strategies.filter((s) => activeIds.includes(s.strategy_id))

  const totalPages = Math.max(1, Math.ceil(activeStrategies.length / PAGE_SIZE))
  const pagedStrategies = activeStrategies.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  return (
    <Card data-testid="active-strategies-panel">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Active Live Strategies</CardTitle>
            <CardDescription>Strategies currently activated for live trading.</CardDescription>
          </div>
          <Badge variant="outline" data-testid="active-count-badge">
            {activeIds.length}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="grid gap-2" data-testid="active-strategies-loading">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        )}

        {!isLoading && activeIds.length === 0 && (
          <p
            className="text-muted-foreground py-4 text-center text-sm"
            data-testid="active-strategies-empty"
          >
            No strategies activated for live trading
          </p>
        )}

        {!isLoading && activeStrategies.length > 0 && (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Template</TableHead>
                  <TableHead>State</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pagedStrategies.map((strategy) => (
                  <TableRow
                    key={strategy.strategy_id}
                    data-testid={`active-strategy-${strategy.strategy_id}`}
                  >
                    <TableCell>
                      <Link
                        to="/strategies/instances/$strategyId"
                        params={{ strategyId: strategy.strategy_id }}
                        className="text-primary hover:underline"
                      >
                        {strategy.name}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {strategy.template_type_id} v{strategy.template_version}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={strategy.actual_state === 'RUNNING' ? 'secondary' : 'outline'}
                        className="text-xs"
                      >
                        {strategy.actual_state}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            {/* Pagination controls — only shown when needed */}
            {totalPages > 1 && (
              <div
                className="flex items-center justify-between pt-3"
                data-testid="active-strategies-pagination"
              >
                <p className="text-muted-foreground text-xs">
                  Page {page + 1} of {totalPages}
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page === 0}
                    onClick={() => setPage((p) => p - 1)}
                    data-testid="pagination-prev"
                  >
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= totalPages - 1}
                    onClick={() => setPage((p) => p + 1)}
                    data-testid="pagination-next"
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </>
        )}

        {/* Show IDs that couldn't be matched (orphans) */}
        {!isLoading && activeIds.length > 0 && activeStrategies.length < activeIds.length && (
          <p className="text-muted-foreground mt-2 text-xs">
            {activeIds.length - activeStrategies.length} activated strategy ID(s) not found in
            registry
          </p>
        )}
      </CardContent>
    </Card>
  )
}
