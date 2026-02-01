import type { ColumnDef } from '@tanstack/react-table'
import { Link } from '@tanstack/react-router'
import { ArrowUpDown } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

import type { StrategyOrderItem } from '@/lib/api'

function formatTs(v: unknown): string {
  if (v == null || v === '' || (typeof v !== 'string' && typeof v !== 'number')) return '—'
  try {
    const d = new Date(v)
    return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
  } catch {
    return '—'
  }
}

export const strategyOrderColumns: ColumnDef<StrategyOrderItem>[] = [
  {
    accessorKey: 'ts_wall',
    meta: { className: 'w-[10rem]' },
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Time
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => (
      <span className="tabular-nums text-muted-foreground text-sm">
        {formatTs(row.getValue('ts_wall'))}
      </span>
    ),
  },
  {
    accessorKey: 'market_slug',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Market
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => {
      const slug = String(row.getValue('market_slug'))
      return (
        <Link
          to="/markets/$marketSlug"
          params={{ marketSlug: slug }}
          className="font-medium hover:underline"
        >
          {slug}
        </Link>
      )
    },
  },
  {
    accessorKey: 'side',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Side
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => (
      <span className="text-muted-foreground">{String(row.getValue('side'))}</span>
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
    accessorKey: 'limit_price',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Limit price
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => (
      <span className="tabular-nums text-right">
        {Number(row.getValue('limit_price')).toFixed(4)}
      </span>
    ),
  },
  {
    accessorKey: 'status',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Status
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => <Badge variant="secondary">{String(row.getValue('status'))}</Badge>,
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
]
