/* eslint-disable react-refresh/only-export-components -- column definitions co-located with cell components */
/**
 * Strategy instance table columns — includes Mode column and expanded
 * actions dropdown per PILOT_LIVE.md Commit 8.
 *
 * Actions dropdown:
 * - Start (safe, no confirm) — when STOPPED or ERROR
 * - Stop (standard confirm) — when RUNNING or STARTING
 * - separator
 * - Activate for Live (typed confirm "ACTIVATE") — when not enabled
 * - Deactivate from Live (standard confirm) — when enabled
 */

import { useState } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { Link } from '@tanstack/react-router'
import { ArrowUpDown, MoreVertical } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { TypedAlertDialog } from '@/components/shared/typed-alert-dialog'
import { useActivateStrategy, useDeactivateStrategy } from '@/hooks/strategy-instances'
import { useStartStrategyMutation, useStopStrategyMutation } from '@/hooks/use-strategy-commands'
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

/** Determine which lifecycle actions are available based on actual_state. */
function canStart(state: string): boolean {
  return state === 'STOPPED' || state === 'ERROR'
}

function canStop(state: string): boolean {
  return state === 'RUNNING' || state === 'STARTING'
}

/**
 * Actions cell: expanded dropdown with lifecycle (start/stop) and
 * activation (activate/deactivate for live) actions.
 */
function StrategyInstanceActionsCell({ strategy }: { strategy: StrategyResponse }) {
  const startMutation = useStartStrategyMutation(strategy.strategy_id)
  const stopMutation = useStopStrategyMutation(strategy.strategy_id)
  const activateMutation = useActivateStrategy(strategy.strategy_id)
  const deactivateMutation = useDeactivateStrategy(strategy.strategy_id)

  const [stopDialogOpen, setStopDialogOpen] = useState(false)
  const [activateDialogOpen, setActivateDialogOpen] = useState(false)
  const [deactivateDialogOpen, setDeactivateDialogOpen] = useState(false)

  const anyPending =
    startMutation.isPending ||
    stopMutation.isPending ||
    activateMutation.isPending ||
    deactivateMutation.isPending

  const state = strategy.actual_state
  const isLive = strategy.enabled

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" className="size-8" aria-label="Open actions menu">
            <MoreVertical className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-44">
          {/* Lifecycle actions */}
          {canStart(state) && (
            <DropdownMenuItem
              onClick={() => startMutation.mutate()}
              disabled={anyPending}
              data-testid="action-start"
            >
              {startMutation.isPending ? 'Starting…' : 'Start'}
            </DropdownMenuItem>
          )}
          {canStop(state) && (
            <DropdownMenuItem
              onClick={() => setStopDialogOpen(true)}
              disabled={anyPending}
              data-testid="action-stop"
            >
              {stopMutation.isPending ? 'Stopping…' : 'Stop'}
            </DropdownMenuItem>
          )}

          <DropdownMenuSeparator />

          {/* Activation actions */}
          {isLive ? (
            <DropdownMenuItem
              onClick={() => setDeactivateDialogOpen(true)}
              disabled={anyPending}
              data-testid="action-deactivate"
            >
              {deactivateMutation.isPending ? 'Deactivating…' : 'Deactivate from Live'}
            </DropdownMenuItem>
          ) : (
            <DropdownMenuItem
              onClick={() => setActivateDialogOpen(true)}
              disabled={anyPending}
              data-testid="action-activate"
            >
              {activateMutation.isPending ? 'Activating…' : 'Activate for Live'}
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Stop confirmation — standard */}
      <TypedAlertDialog
        open={stopDialogOpen}
        onOpenChange={setStopDialogOpen}
        title="Stop Strategy"
        description={`Stop "${strategy.name}"? This will halt signal generation and order placement.`}
        confirmLabel="Stop Strategy"
        isPending={stopMutation.isPending}
        onConfirm={() => {
          stopMutation.mutate(undefined, {
            onSuccess: () => setStopDialogOpen(false),
          })
        }}
      />

      {/* Activate for Live — typed confirmation */}
      <TypedAlertDialog
        open={activateDialogOpen}
        onOpenChange={setActivateDialogOpen}
        title="Activate for Live Trading"
        description={`Activate "${strategy.name}" (${strategy.template_type_id} v${strategy.template_version}) for live trading. This strategy will be eligible for real order execution when execution is enabled.`}
        confirmLabel="Activate"
        confirmWord="ACTIVATE"
        isPending={activateMutation.isPending}
        onConfirm={() => {
          activateMutation.mutate(undefined, {
            onSuccess: () => setActivateDialogOpen(false),
          })
        }}
      />

      {/* Deactivate from Live — standard confirmation */}
      <TypedAlertDialog
        open={deactivateDialogOpen}
        onOpenChange={setDeactivateDialogOpen}
        title="Deactivate from Live Trading"
        description={`Remove "${strategy.name}" from live trading. It will continue running in paper mode only.`}
        confirmLabel="Deactivate"
        isPending={deactivateMutation.isPending}
        onConfirm={() => {
          deactivateMutation.mutate(undefined, {
            onSuccess: () => setDeactivateDialogOpen(false),
          })
        }}
      />
    </>
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
    accessorKey: 'enabled',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Mode
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => {
      const isLive = Boolean(row.getValue('enabled'))
      return (
        <Badge
          variant={isLive ? 'destructive' : 'secondary'}
          data-testid={`mode-badge-${row.original.strategy_id}`}
        >
          {isLive ? 'LIVE' : 'PAPER'}
        </Badge>
      )
    },
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
