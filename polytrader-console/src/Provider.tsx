import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import type { FC, ReactNode } from 'react'

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 60 * 1000,
      },
    },
  })

interface ProviderProps {
  children: ReactNode
}

export const Provider: FC<ProviderProps> = ({ children }) => {
  const [queryClient] = useState(createQueryClient)
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}
