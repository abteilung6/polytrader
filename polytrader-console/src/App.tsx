import { useEffect, useState } from 'react'
import type { FC } from 'react'
import type { MarketsResponse } from './lib/api'
import { marketApi } from './lib/api-client'

const App: FC = () => {
  const [data, setData] = useState<MarketsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    marketApi
      .getMarketsApiV1MarketMarketsGet()
      .then((res) => setData(res.data))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p>Loading…</p>
  if (error) return <p>Error: {error}</p>
  if (!data) return null

  return (
    <pre style={{ padding: '1rem', textAlign: 'left', overflow: 'auto' }}>
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}

export default App
