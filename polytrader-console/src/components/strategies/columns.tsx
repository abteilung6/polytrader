import type { ColumnDef } from '@tanstack/react-table'
import { ArrowUpDown } from 'lucide-react'

import { Button } from '@/components/ui/button'

import type { StrategyTypeResponse } from '@/lib/api'

/** Latest version from available_versions (last element). */
function latestVersion(versions: string[]): string | null {
  if (!versions?.length) return null
  return versions[versions.length - 1] ?? null
}

export const strategyTemplateColumns: ColumnDef<StrategyTypeResponse>[] = [
  {
    accessorKey: 'type_id',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Type ID
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => <span className="font-medium">{row.getValue('type_id')}</span>,
  },
  {
    accessorKey: 'name',
    header: ({ column }) => (
      <Button variant="ghost" onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}>
        Name
        <ArrowUpDown className="ml-2 size-4" />
      </Button>
    ),
    cell: ({ row }) => <span>{row.getValue('name')}</span>,
  },
  {
    id: 'latest_available_versions',
    header: 'Latest version',
    accessorFn: (row) => latestVersion(row.available_versions ?? []),
    cell: ({ row }) => {
      const v = latestVersion(row.original.available_versions ?? [])
      return <span className="text-muted-foreground">{v ?? '—'}</span>
    },
  },
]
