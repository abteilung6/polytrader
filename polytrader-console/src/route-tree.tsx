import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  redirect,
} from '@tanstack/react-router'
import { MarketDetailPage } from '@/pages/market-detail'
import { MarketsPage } from '@/pages/markets'
import { StrategiesTemplatesPage } from '@/pages/strategies-templates'
import { StrategiesInstancesPage } from '@/pages/strategies-instances'

const rootRoute = createRootRoute({
  component: () => <Outlet />,
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  beforeLoad: () => {
    // TanStack Router redirect() is thrown for control flow; not an Error instance
    // eslint-disable-next-line @typescript-eslint/only-throw-error -- framework API
    throw redirect({ to: '/markets' })
  },
})

const marketsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/markets',
  component: MarketsPage,
})

const marketDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/markets/$marketSlug',
  component: MarketDetailPage,
})

const strategiesTemplatesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/strategies/templates',
  component: StrategiesTemplatesPage,
})

const strategiesInstancesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/strategies/instances',
  component: StrategiesInstancesPage,
})

export const routeTree = rootRoute.addChildren([
  indexRoute,
  marketsRoute,
  marketDetailRoute,
  strategiesTemplatesRoute,
  strategiesInstancesRoute,
])

export const router = createRouter({ routeTree })
