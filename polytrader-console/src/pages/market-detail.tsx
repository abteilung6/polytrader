import type { FC } from 'react'
import { useParams } from '@tanstack/react-router'

export const MarketDetailPage: FC = () => {
  const { marketSlug } = useParams({ strict: false })
  return (
    <div className="flex min-h-svh flex-col items-center justify-center bg-background p-4">
      <p className="text-muted-foreground">Market: {marketSlug ?? '—'}</p>
    </div>
  )
}
