import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  redirect,
} from '@tanstack/react-router'
import { LayoutComponent, NotFound } from '@/route-components'
import { ControlPage } from '@/pages/control'
import { MarketDetailPage } from '@/pages/market-detail'
import { MarketsPage } from '@/pages/markets'
import { LiveTradingPage } from '@/pages/live-trading'
import { PerformancePage } from '@/pages/performance'
import { StrategyInstanceDetailPage } from '@/pages/strategy-instance-detail'
import { StrategiesInstancesPage } from '@/pages/strategies-instances'
import { StrategiesTemplatesPage } from '@/pages/strategies-templates'

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
  component: () => <Outlet />,
})

const marketsIndexRoute = createRoute({
  getParentRoute: () => marketsRoute,
  path: '/',
  component: MarketsPage,
})

const marketDetailRoute = createRoute({
  getParentRoute: () => marketsRoute,
  path: '$marketSlug',
  component: MarketDetailPage,
})

const performanceRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: 'performance',
  component: () => <Outlet />,
})

const performanceIndexRoute = createRoute({
  getParentRoute: () => performanceRoute,
  path: '/',
  beforeLoad: () => {
    // TanStack Router redirect() is thrown for control flow; not an Error instance
    // eslint-disable-next-line @typescript-eslint/only-throw-error -- framework API
    throw redirect({ to: '/performance/paper' })
  },
})

const performancePaperRoute = createRoute({
  getParentRoute: () => performanceRoute,
  path: 'paper',
  component: PerformancePage,
})

const performanceLiveRoute = createRoute({
  getParentRoute: () => performanceRoute,
  path: 'live',
  validateSearch: (search: Record<string, unknown>): { tab?: 'strategies' | 'orders' } => {
    const tab = search.tab
    if (tab === 'strategies' || tab === 'orders') return { tab }
    return {}
  },
  component: LiveTradingPage,
})

const controlRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: 'control',
  component: ControlPage,
})

const strategiesTemplatesRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: 'strategies/templates',
  component: StrategiesTemplatesPage,
})

const strategiesInstancesRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: 'strategies/instances',
  component: () => <Outlet />,
})

const strategiesInstancesIndexRoute = createRoute({
  getParentRoute: () => strategiesInstancesRoute,
  path: '/',
  component: StrategiesInstancesPage,
})

const strategyInstanceDetailRoute = createRoute({
  getParentRoute: () => strategiesInstancesRoute,
  path: '$strategyId',
  validateSearch: (
    search: Record<string, unknown>,
  ): { tab?: 'signals' | 'orders' | 'performance' } => {
    const tab = search.tab
    if (tab === 'signals' || tab === 'orders' || tab === 'performance') return { tab }
    return {}
  },
  component: StrategyInstanceDetailPage,
})

export const routeTree = rootRoute.addChildren([
  layoutRoute.addChildren([
    indexRoute,
    marketsRoute.addChildren([marketsIndexRoute, marketDetailRoute]),
    performanceRoute.addChildren([
      performanceIndexRoute,
      performancePaperRoute,
      performanceLiveRoute,
    ]),
    controlRoute,
    strategiesTemplatesRoute,
    strategiesInstancesRoute.addChildren([
      strategiesInstancesIndexRoute,
      strategyInstanceDetailRoute,
    ]),
  ]),
])

export const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
