import type { ColumnDef } from '@tanstack/react-table'
import { Link } from '@tanstack/react-router'
import { ArrowUpDown } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'

import type { MarketInfoResponse } from '@/lib/api'

export const marketColumns: ColumnDef<MarketInfoResponse>[] = [
  {
    id: 'select',
    header: ({ table }) => (
      <Checkbox
        checked={
          table.getIsAllPageRowsSelected() || (table.getIsSomePageRowsSelected() && 'indeterminate')
        }
        onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
        aria-label="Select all"
      />
    ),
    cell: ({ row }) => (
      <Checkbox
        checked={row.getIsSelected()}
        onCheckedChange={(value) => row.toggleSelected(!!value)}
        aria-label="Select row"
      />
    ),
    enableSorting: false,
    enableHiding: false,
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
    cell: ({ row }) => <div>{row.getValue('outcome')}</div>,
  },
  {
    accessorKey: 'start_date',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Start date
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => {
      const v = row.getValue('start_date')
      if (v == null || v === '') return <span className="text-muted-foreground">—</span>
      try {
        const d = new Date(v)
        return <span className="tabular-nums">{d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })}</span>
      } catch {
        return <span className="text-muted-foreground">—</span>
      }
    },
  },
  {
    accessorKey: 'end_date',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        End date
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => {
      const v = row.getValue('end_date')
      if (v == null || v === '') return <span className="text-muted-foreground">—</span>
      try {
        const d = new Date(v)
        return <span className="tabular-nums">{d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })}</span>
      } catch {
        return <span className="text-muted-foreground">—</span>
      }
    },
  },
  {
    accessorKey: 'active',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Active
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => {
      const active = Boolean(row.getValue('active'))
      return (
        <Badge variant={active ? 'default' : 'secondary'}>{active ? 'Active' : 'Inactive'}</Badge>
      )
    },
  },
]
