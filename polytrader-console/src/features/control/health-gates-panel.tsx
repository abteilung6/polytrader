/**
 * Health gates panel — displays system health gate statuses.
 *
 * Per PILOT_LIVE.md §5.1: Pre-session system health check.
 * The operator verifies all gates are green before enabling execution.
 *
 * Gates: database, market_data_freshness, event_bus_lag,
 *        venue_connectivity, risk_engine
 * Statuses: ok (green), degraded (yellow), down (red)
 */

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
import { useHealthGatesQuery } from '@/hooks/use-health-gates'
import type { HealthGateStatus } from '@/lib/api'

const GATE_LABELS: Record<string, string> = {
  db: 'Database',
  market_data_freshness: 'Market Data',
  event_bus_lag: 'Event Bus',
  venue_connectivity: 'Venue API',
  risk_engine: 'Risk Engine',
}

function statusIndicator(status: string): string {
  switch (status) {
    case 'ok':
      return '🟢'
    case 'degraded':
      return '🟡'
    case 'down':
      return '🔴'
    default:
      return '⚪'
  }
}

function overallBadgeVariant(overall: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (overall) {
    case 'ok':
      return 'secondary'
    case 'degraded':
      return 'outline'
    case 'down':
      return 'destructive'
    default:
      return 'outline'
  }
}

export function HealthGatesPanel() {
  const { data, isLoading, error } = useHealthGatesQuery()

  return (
    <Card data-testid="health-gates-panel">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Health Gates</CardTitle>
            <CardDescription>
              System health checks — all gates must pass before enabling execution.
            </CardDescription>
          </div>
          {data && (
            <Badge variant={overallBadgeVariant(data.overall)} data-testid="health-overall-badge">
              {data.overall.toUpperCase()}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="grid gap-2" data-testid="health-loading">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        )}

        {error && (
          <p className="text-destructive text-sm" data-testid="health-error">
            Failed to load health gates: {error.message}
          </p>
        )}

        {data && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8"></TableHead>
                <TableHead>Gate</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Detail</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {Object.entries(data.gates).map(([key, gate]) => {
                if (key === 'clock_skew_ms') return null
                const gateStatus = gate as HealthGateStatus
                return (
                  <TableRow key={key} data-testid={`health-gate-${key}`}>
                    <TableCell className="text-center">
                      {statusIndicator(gateStatus.status)}
                    </TableCell>
                    <TableCell className="font-medium">{GATE_LABELS[key] ?? key}</TableCell>
                    <TableCell>
                      <Badge variant={overallBadgeVariant(gateStatus.status)} className="text-xs">
                        {gateStatus.status.toUpperCase()}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {gateStatus.message ?? '—'}
                    </TableCell>
                  </TableRow>
                )
              })}
              {/* Clock skew as a separate info row */}
              {data.gates.clock_skew_ms !== undefined && (
                <TableRow data-testid="health-gate-clock_skew">
                  <TableCell className="text-center">
                    {Math.abs(data.gates.clock_skew_ms) < 1000 ? '🟢' : '🟡'}
                  </TableCell>
                  <TableCell className="font-medium">Clock Skew</TableCell>
                  <TableCell>
                    <Badge
                      variant={Math.abs(data.gates.clock_skew_ms) < 1000 ? 'secondary' : 'outline'}
                      className="text-xs"
                    >
                      {Math.abs(data.gates.clock_skew_ms) < 1000 ? 'OK' : 'DRIFT'}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {data.gates.clock_skew_ms}ms
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
