import type { ColumnDef } from '@tanstack/react-table'
import { Link } from '@tanstack/react-router'
import { ArrowUpDown } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

import type { StrategyResponse } from '@/lib/api'

function formatCreatedAt(v: unknown): string {
  if (v == null || v === '' || (typeof v !== 'string' && typeof v !== 'number')) return '—'
  try {
    const d = new Date(v)
    return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
  } catch {
    return '—'
  }
}

export const strategyInstanceColumns: ColumnDef<StrategyResponse>[] = [
  {
    accessorKey: 'strategy_id',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Strategy ID
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => <span className="font-medium">{row.getValue('strategy_id')}</span>,
  },
  {
    accessorKey: 'name',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Name
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => {
      const strategy = row.original
      return (
        <Link
          to="/strategies/instances/$strategyId"
          params={{ strategyId: strategy.strategy_id }}
          className="font-medium hover:underline"
        >
          {row.getValue('name')}
        </Link>
      )
    },
  },
  {
    accessorKey: 'template_type_id',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Template type ID
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => (
      <span className="text-muted-foreground">{row.getValue('template_type_id')}</span>
    ),
  },
  {
    accessorKey: 'template_version',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Template version
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => (
      <span className="text-muted-foreground">{row.getValue('template_version')}</span>
    ),
  },
  {
    accessorKey: 'actual_state',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Actual state
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => <Badge variant="secondary">{String(row.getValue('actual_state'))}</Badge>,
  },
  {
    accessorKey: 'created_at',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Created at
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => (
      <span className="tabular-nums text-muted-foreground">
        {formatCreatedAt(row.getValue('created_at'))}
      </span>
    ),
  },
]
