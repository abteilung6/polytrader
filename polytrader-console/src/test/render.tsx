import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, type RenderOptions } from '@testing-library/react'
import type { ReactElement, ReactNode } from 'react'
import { routeTree } from '@/routes'

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

/**
 * Renders a specific component inside QueryClient + a minimal TanStack Router context.
 * Use for components that use Link/useParams but are NOT full route-level pages.
 * The component is rendered as the root route's component.
 */
export const renderWithQueryAndRouter = (
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>,
) => {
  const queryClient = createTestQueryClient()
  const root = createRootRoute({ component: () => ui })
  const tree = root.addChildren([])
  const history = createMemoryHistory({ initialEntries: ['/'] })
  const testRouter = createRouter({ routeTree: tree, history })
  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={testRouter} />
    </QueryClientProvider>,
    options,
  )
}

export interface RenderWithRouterOptions extends Omit<RenderOptions, 'wrapper'> {
  initialEntries?: string[]
  initialIndex?: number
}

/**
 * Renders UI with QueryClientProvider + TanStack Router (memory history).
 * Use for pages or components that depend on router APIs (Link, useParams, etc.).
 * Default initial route: /markets.
 */
export const renderWithRouter = (options?: RenderWithRouterOptions) => {
  const { initialEntries = ['/markets'], initialIndex = 0, ...renderOptions } = options ?? {}
  const queryClient = createTestQueryClient()
  const history = createMemoryHistory({ initialEntries, initialIndex })
  const testRouter = createRouter({ routeTree, history })
  const Wrapper = ({ children }: WrapperProps) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return render(<RouterProvider router={testRouter} />, {
    wrapper: Wrapper,
    ...renderOptions,
  })
}
