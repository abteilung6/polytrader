import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, type RenderOptions } from '@testing-library/react'
import type { ReactElement, ReactNode } from 'react'

export const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  })

interface WrapperProps {
  children: ReactNode
}

export const renderWithQuery = (ui: ReactElement, options?: Omit<RenderOptions, 'wrapper'>) => {
  const queryClient = createTestQueryClient()
  const Wrapper = ({ children }: WrapperProps) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return render(ui, { wrapper: Wrapper, ...options })
}
