import type { ColumnDef } from '@tanstack/react-table'
import { Link } from '@tanstack/react-router'
import { ArrowUpDown } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { PerformanceOverviewItemResponse } from '@/lib/api'

function formatPnl(value: number): string {
  const prefix = value >= 0 ? '+' : ''
  return `${prefix}${value.toFixed(2)}`
}

function formatPct(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${value.toFixed(1)}%`
}

function formatOptionalNumber(value: number | null | undefined, decimals = 2): string {
  if (value == null) return '—'
  return value.toFixed(decimals)
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString(undefined, {
      dateStyle: 'short',
      timeStyle: 'short',
    })
  } catch {
    return '—'
  }
}

export const performanceOverviewColumns: ColumnDef<PerformanceOverviewItemResponse>[] = [
  {
    accessorKey: 'name',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Strategy
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => {
      const item = row.original
      return (
        <Link
          to="/strategies/instances/$strategyId"
          params={{ strategyId: item.strategy_id }}
          search={{ tab: 'performance' }}
          className="font-medium hover:underline"
        >
          {item.name}
        </Link>
      )
    },
  },
  {
    accessorKey: 'template_type_id',
    header: 'Template',
    cell: ({ row }) => (
      <span className="text-muted-foreground">{row.getValue('template_type_id')}</span>
    ),
  },
  {
    accessorKey: 'actual_state',
    header: 'State',
    cell: ({ row }) => <Badge variant="secondary">{String(row.getValue('actual_state'))}</Badge>,
  },
  {
    accessorKey: 'trade_count',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Trades
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => <span className="tabular-nums">{row.getValue<number>('trade_count')}</span>,
  },
  {
    accessorKey: 'wins',
    header: 'W',
    cell: ({ row }) => (
      <span className="tabular-nums text-green-600">{row.getValue<number>('wins')}</span>
    ),
  },
  {
    accessorKey: 'losses',
    header: 'L',
    cell: ({ row }) => (
      <span className="tabular-nums text-red-600">{row.getValue<number>('losses')}</span>
    ),
  },
  {
    accessorKey: 'win_rate_pct',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Win %
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => (
      <span className="tabular-nums">{formatPct(row.getValue<number | null>('win_rate_pct'))}</span>
    ),
  },
  {
    accessorKey: 'total_realized_pnl',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Total PnL
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => {
      const pnl = row.getValue<number>('total_realized_pnl')
      return (
        <span
          className={`tabular-nums font-medium ${pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}
        >
          {formatPnl(pnl)}
        </span>
      )
    },
  },
  {
    accessorKey: 'avg_trade_pnl',
    header: 'Avg PnL',
    cell: ({ row }) => (
      <span className="tabular-nums">
        {formatOptionalNumber(row.getValue<number | null>('avg_trade_pnl'))}
      </span>
    ),
  },
  {
    accessorKey: 'profit_factor',
    header: 'PF',
    cell: ({ row }) => (
      <span className="tabular-nums">
        {formatOptionalNumber(row.getValue<number | null>('profit_factor'))}
      </span>
    ),
  },
  {
    accessorKey: 'evidence_tier',
    header: 'Evidence',
    cell: ({ row }) => {
      const tier = row.getValue<string>('evidence_tier')
      const variant = tier === 'TRACKING' ? 'default' : 'secondary'
      const label = tier === 'TRACKING' ? 'Tracking' : 'Insufficient'
      return <Badge variant={variant}>{label}</Badge>
    },
  },
  {
    accessorKey: 'last_trade_exit_ts_wall',
    header: 'Last Trade',
    cell: ({ row }) => (
      <span className="tabular-nums text-muted-foreground">
        {formatTimestamp(row.getValue<string | null>('last_trade_exit_ts_wall'))}
      </span>
    ),
  },
]
