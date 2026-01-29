import type { FC } from 'react'
import { useMarketsQuery } from './hooks/markets'

const App: FC = () => {
  const { data, isPending, error } = useMarketsQuery({
    pattern: 'btc-updown-15m',
  })

  if (isPending) return <p>Loading…</p>
  if (error) return <p>Error: {error instanceof Error ? error.message : String(error)}</p>
  if (!data) return null

  return (
    <pre style={{ padding: '1rem', textAlign: 'left', overflow: 'auto' }}>
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}

export default App
