import type { FC } from 'react'

import type { PerformanceSummary } from '@/lib/api'

interface PerformanceSummaryCardsProps {
  summary: PerformanceSummary | undefined
  isPending?: boolean
}

export const PerformanceSummaryCards: FC<PerformanceSummaryCardsProps> = ({
  summary,
  isPending = false,
}) => {
  const totalPnl = summary?.total_realized_pnl ?? 0
  const totalTrades = summary?.total_trades ?? 0
  const winRatePct = summary?.win_rate_pct ?? null

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <div className="rounded-lg border bg-card p-4">
        <p className="text-muted-foreground text-sm">Total realized P&L</p>
        {isPending ? (
          <p className="text-muted-foreground text-lg font-semibold">—</p>
        ) : (
          <p
            className={
              totalPnl > 0
                ? 'text-lg font-semibold text-green-600'
                : totalPnl < 0
                  ? 'text-lg font-semibold text-red-600'
                  : 'text-lg font-semibold'
            }
          >
            {totalPnl.toFixed(2)} USD
          </p>
        )}
      </div>
      <div className="rounded-lg border bg-card p-4">
        <p className="text-muted-foreground text-sm">Total trades</p>
        <p className="text-lg font-semibold">{isPending ? '—' : totalTrades}</p>
      </div>
      <div className="rounded-lg border bg-card p-4">
        <p className="text-muted-foreground text-sm">Win rate</p>
        <p className="text-lg font-semibold">
          {isPending ? '—' : winRatePct != null ? `${winRatePct.toFixed(1)}%` : '—'}
        </p>
      </div>
    </div>
  )
}
