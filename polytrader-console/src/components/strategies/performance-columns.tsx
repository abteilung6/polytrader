import type { ColumnDef } from '@tanstack/react-table'
import { ArrowUpDown } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

import type { ClosedTradeItem } from '@/lib/api'

function formatTs(v: unknown): string {
  if (v == null || v === '' || (typeof v !== 'string' && typeof v !== 'number')) return '—'
  try {
    const d = new Date(v)
    return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
  } catch {
    return '—'
  }
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}m ${s.toFixed(0)}s`
}

export const strategyPerformanceColumns: ColumnDef<ClosedTradeItem>[] = [
  {
    accessorKey: 'market_slug',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Market
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => <span className="font-medium">{row.getValue('market_slug')}</span>,
  },
  {
    accessorKey: 'outcome',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Outcome
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => <span className="text-muted-foreground">{row.getValue('outcome')}</span>,
  },
  {
    accessorKey: 'exit_ts_wall',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Exit time
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => (
      <span className="tabular-nums text-muted-foreground text-sm">
        {formatTs(row.getValue('exit_ts_wall'))}
      </span>
    ),
  },
  {
    accessorKey: 'entry_price',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Entry
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => (
      <span className="tabular-nums text-right">
        {Number(row.getValue('entry_price')).toFixed(4)}
      </span>
    ),
  },
  {
    accessorKey: 'exit_price',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Exit
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => (
      <span className="tabular-nums text-right">
        {Number(row.getValue('exit_price')).toFixed(4)}
      </span>
    ),
  },
  {
    accessorKey: 'size',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Size
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => (
      <span className="tabular-nums text-right">{Number(row.getValue('size')).toFixed(2)}</span>
    ),
  },
  {
    accessorKey: 'pnl',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        P&L (USD)
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => {
      const pnl = Number(row.getValue('pnl'))
      return (
        <span
          className={
            pnl > 0
              ? 'tabular-nums text-right text-green-600'
              : pnl < 0
                ? 'tabular-nums text-right text-red-600'
                : 'tabular-nums text-right text-muted-foreground'
          }
        >
          {pnl.toFixed(2)}
        </span>
      )
    },
  },
  {
    accessorKey: 'pnl_pct',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        P&L %
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => {
      const pct = Number(row.getValue('pnl_pct'))
      return (
        <span
          className={
            pct > 0
              ? 'tabular-nums text-right text-green-600'
              : pct < 0
                ? 'tabular-nums text-right text-red-600'
                : 'tabular-nums text-right text-muted-foreground'
          }
        >
          {pct.toFixed(2)}%
        </span>
      )
    },
  },
  {
    accessorKey: 'result',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Result
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => {
      const result = String(row.getValue('result'))
      return (
        <Badge
          variant={result === 'WIN' ? 'default' : result === 'LOSS' ? 'destructive' : 'secondary'}
        >
          {result}
        </Badge>
      )
    },
  },
  {
    accessorKey: 'execution_mode',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Mode
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => {
      const mode = row.getValue('execution_mode')
      return (
        <Badge variant={mode === 'live' ? 'default' : 'outline'}>
          {mode === 'live' ? 'Live' : 'Paper'}
        </Badge>
      )
    },
  },
  {
    accessorKey: 'duration_seconds',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Duration
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => (
      <span className="tabular-nums text-muted-foreground text-sm">
        {formatDuration(Number(row.getValue('duration_seconds')))}
      </span>
    ),
  },
]
