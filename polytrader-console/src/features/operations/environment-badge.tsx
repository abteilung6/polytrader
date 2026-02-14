/**
 * Environment badge — shows PAPER or LIVE in the site header.
 *
 * Per PILOT_LIVE.md §5 / §8.4: The operator must always see which mode
 * the platform is in. This badge is visible on every page.
 *
 * - PAPER (variant=secondary) when execution is disabled
 * - LIVE  (variant=destructive, red) when execution is enabled
 *
 * Uses useExecutionStateQuery() for reactive polling.
 */

import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useExecutionStateQuery } from '@/hooks/use-execution-state'

export function EnvironmentBadge() {
  const { data, isLoading } = useExecutionStateQuery()

  if (isLoading) {
    return <Skeleton className="h-5 w-14 rounded-full" data-testid="env-badge-skeleton" />
  }

  const isLive = data?.execution_enabled ?? false

  return (
    <Badge
      variant={isLive ? 'destructive' : 'secondary'}
      data-testid="environment-badge"
      aria-label={isLive ? 'Live execution mode' : 'Paper trading mode'}
    >
      {isLive ? 'LIVE' : 'PAPER'}
    </Badge>
  )
}
