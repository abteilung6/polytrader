import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  redirect,
} from '@tanstack/react-router'
import { LayoutComponent, NotFound } from '@/route-components'
import { MarketsPage } from '@/pages/markets'
import { MarketDetailPage } from '@/pages/market-detail'

const rootRoute = createRootRoute({
  component: () => <Outlet />,
  notFoundComponent: NotFound,
})

const layoutRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'layout',
  component: LayoutComponent,
})

const indexRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/',
  beforeLoad: () => {
    // TanStack Router redirect() is thrown for control flow; not an Error instance
    // eslint-disable-next-line @typescript-eslint/only-throw-error -- framework API
    throw redirect({ to: '/markets' })
  },
})

const marketsRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: 'markets',
  component: MarketsPage,
})

const marketDetailRoute = createRoute({
  getParentRoute: () => marketsRoute,
  path: '$marketSlug',
  component: MarketDetailPage,
})

const routeTree = rootRoute.addChildren([
  layoutRoute.addChildren([indexRoute, marketsRoute.addChildren([marketDetailRoute])]),
])

export const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
