import type { ColumnDef } from '@tanstack/react-table'
import { Link } from '@tanstack/react-router'
import { ArrowUpDown } from 'lucide-react'

import { Button } from '@/components/ui/button'

import type { StrategySignalItem } from '@/lib/api'

function formatTs(v: unknown): string {
  if (v == null || v === '' || (typeof v !== 'string' && typeof v !== 'number')) return '—'
  try {
    const d = new Date(v)
    return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
  } catch {
    return '—'
  }
}

function formatPct(n: number): string {
  return `${(n * 100).toFixed(2)}%`
}

function formatNum(n: number, decimals = 4): string {
  return n.toFixed(decimals)
}

export const strategySignalColumns: ColumnDef<StrategySignalItem>[] = [
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
    accessorKey: 'outcome',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Outcome
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => (
      <span className="text-muted-foreground">{String(row.getValue('outcome'))}</span>
    ),
  },
  {
    accessorKey: 'p_up',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        P(up)
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => (
      <span className="tabular-nums text-right">{formatPct(Number(row.getValue('p_up')))}</span>
    ),
  },
  {
    accessorKey: 'p_down',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        P(down)
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => (
      <span className="tabular-nums text-right">{formatPct(Number(row.getValue('p_down')))}</span>
    ),
  },
  {
    accessorKey: 'edge',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Edge
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => (
      <span className="tabular-nums text-right">{formatNum(Number(row.getValue('edge')))}</span>
    ),
  },
  {
    accessorKey: 'confidence',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Confidence
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => (
      <span className="tabular-nums text-right">
        {formatPct(Number(row.getValue('confidence')))}
      </span>
    ),
  },
  {
    accessorKey: 'rationale',
    header: 'Rationale',
    cell: ({ row }) => {
      const v = row.original.rationale
      if (v == null || v === '') return <span className="text-muted-foreground">—</span>
      const s = String(v)
      const truncated = s.length > 60 ? `${s.slice(0, 60)}…` : s
      return <span className="text-muted-foreground text-sm">{truncated}</span>
    },
  },
]
