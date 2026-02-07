/* eslint-disable react-refresh/only-export-components -- column definitions co-located with cell components */
import type { ColumnDef } from '@tanstack/react-table'
import { Link } from '@tanstack/react-router'
import { ArrowUpDown, MoreVertical } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useActivateStrategy, useDeactivateStrategy } from '@/hooks/strategy-instances'
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

/** Actions cell: dropdown always has one item — Enable when disabled, Disable when enabled. Source of truth: StrategyResponse.enabled (from GET /api/v1/state/strategies). */
function StrategyInstanceActionsCell({ strategy }: { strategy: StrategyResponse }) {
  const activateMutation = useActivateStrategy(strategy.strategy_id)
  const deactivateMutation = useDeactivateStrategy(strategy.strategy_id)
  const isPending = activateMutation.isPending || deactivateMutation.isPending

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="size-8" aria-label="Open actions menu">
          <MoreVertical className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-32">
        {strategy.enabled ? (
          <DropdownMenuItem onClick={() => deactivateMutation.mutate()} disabled={isPending}>
            {deactivateMutation.isPending ? 'Disabling…' : 'Disable'}
          </DropdownMenuItem>
        ) : (
          <DropdownMenuItem onClick={() => activateMutation.mutate()} disabled={isPending}>
            {activateMutation.isPending ? 'Enabling…' : 'Enable'}
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
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
  {
    id: 'actions',
    header: 'Actions',
    cell: ({ row }) => <StrategyInstanceActionsCell strategy={row.original} />,
    enableSorting: false,
    enableHiding: false,
  },
]
