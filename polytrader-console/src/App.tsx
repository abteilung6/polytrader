import type { FC } from 'react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useMarketsQuery } from './hooks/markets'
import type { MarketInfoResponse } from './lib/api'

const App: FC = () => {
  const { data, isPending, error } = useMarketsQuery({
    pattern: 'btc-updown-15m',
  })

  if (isPending) {
    return (
      <div className="flex min-h-svh flex-col items-center justify-center bg-background">
        <p className="text-muted-foreground">Loading…</p>
      </div>
    )
  }
  if (error) {
    return (
      <div className="flex min-h-svh flex-col items-center justify-center bg-background p-4">
        <p className="text-destructive">
          Error: {error instanceof Error ? error.message : String(error)}
        </p>
      </div>
    )
  }
  if (!data) return null

  const markets: MarketInfoResponse[] = data.markets ?? []

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Market</TableHead>
          <TableHead>Outcome</TableHead>
          <TableHead>Latest tick</TableHead>
          <TableHead>Active</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {markets.length === 0 ? (
          <TableRow>
            <TableCell colSpan={4} className="text-center text-muted-foreground">
              No markets
            </TableCell>
          </TableRow>
        ) : (
          markets.map((m) => (
            <TableRow key={`${m.market_slug}-${m.outcome}`}>
              <TableCell>{m.market_slug}</TableCell>
              <TableCell>{m.outcome}</TableCell>
              <TableCell>{m.latest_tick_ts ?? '—'}</TableCell>
              <TableCell>{m.active ? 'Yes' : 'No'}</TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  )
}

export default App
