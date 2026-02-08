import { screen } from '@testing-library/react'
import { vi } from 'vitest'

import { controlApi } from '@/lib/api-client'
import {
  createMockPerformanceOverviewResponse,
  createMockStrategyOrderItem,
  createMockStrategyOrdersResponse,
  createMockStrategyResponse,
  createMockStrategiesResponse,
} from '@/test/mocks'
import { mockAxiosResponse, renderWithRouter } from '@/test/utils'

function mockLiveDashboardApis(
  overrides: {
    activeStrategies?: string[]
    strategies?: ReturnType<typeof createMockStrategyResponse>[]
    performanceItems?: number
    ordersPerStrategy?: {
      strategyId: string
      items: ReturnType<typeof createMockStrategyOrderItem>[]
    }[]
  } = {},
) {
  const activeStrategies = overrides.activeStrategies ?? []
  const strategies =
    overrides.strategies ??
    activeStrategies.map((id) =>
      createMockStrategyResponse({
        strategy_id: id,
        name: `Strategy ${id}`,
        enabled: true,
        actual_state: 'RUNNING',
      }),
    )
  const performanceItems = overrides.performanceItems ?? 0
  const ordersPerStrategy = overrides.ordersPerStrategy ?? []

  vi.spyOn(controlApi, 'getLiveStrategiesApiV1StateLiveStrategiesGet').mockResolvedValue(
    mockAxiosResponse({ data: { active_strategies: activeStrategies } }),
  )
  vi.spyOn(controlApi, 'getStrategiesApiV1StateStrategiesGet').mockResolvedValue(
    mockAxiosResponse({ data: createMockStrategiesResponse({ strategies }) }),
  )
  vi.spyOn(
    controlApi,
    'getPerformanceOverviewApiV1StateStrategiesPerformanceOverviewGet',
  ).mockResolvedValue(
    mockAxiosResponse({
      data: createMockPerformanceOverviewResponse({
        items: Array.from({ length: performanceItems }, (_, i) => ({
          strategy_id: `strat-${i}`,
          name: `Strategy ${i}`,
          template_type_id: 'vfmr',
          template_version: '1.0',
          actual_state: 'RUNNING',
          trade_count: 1,
          wins: 1,
          losses: 0,
          breakevens: 0,
          total_realized_pnl: 10,
          evidence_tier: 'TRACKING' as const,
        })),
      }),
    }),
  )

  const getOrdersSpy = vi.spyOn(
    controlApi,
    'getStrategyOrdersApiV1StateStrategiesStrategyIdOrdersGet',
  )
  if (ordersPerStrategy.length > 0) {
    const byStrategyId = new Map(
      ordersPerStrategy.map(({ strategyId, items }) => [strategyId, items]),
    )
    getOrdersSpy.mockImplementation((params: { strategyId: string }) =>
      Promise.resolve(
        mockAxiosResponse({
          data: createMockStrategyOrdersResponse({
            items: byStrategyId.get(params.strategyId) ?? [],
          }),
        }),
      ),
    )
  } else if (activeStrategies.length > 0) {
    getOrdersSpy.mockResolvedValue(
      mockAxiosResponse({ data: createMockStrategyOrdersResponse({ items: [] }) }),
    )
  }
}

describe('LiveTradingPage', () => {
  it('renders Live Trading dashboard with summary cards and Orders tab', async () => {
    mockLiveDashboardApis()
    renderWithRouter({ initialEntries: ['/performance/live'] })
    expect(await screen.findByTestId('live-summary-cards')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Orders' })).toBeInTheDocument()
    expect(await screen.findByTestId('live-orders-table')).toBeInTheDocument()
  })

  it('renders summary cards with correct counts', async () => {
    mockLiveDashboardApis({
      activeStrategies: ['s1', 's2'],
      performanceItems: 2,
    })
    renderWithRouter({ initialEntries: ['/performance/live'] })
    const cards = await screen.findByTestId('live-summary-cards')
    expect(cards).toBeInTheDocument()
    expect(await screen.findByTestId('count-active-strategies')).toHaveTextContent('2')
    expect(await screen.findByTestId('count-open-orders')).toHaveTextContent('0')
    expect(await screen.findByTestId('count-positions')).toHaveTextContent('—')
    expect(await screen.findByTestId('total-live-pnl')).toBeInTheDocument()
  })

  it('live orders table shows empty state when no live orders', async () => {
    mockLiveDashboardApis({ activeStrategies: ['s1'] })
    renderWithRouter({ initialEntries: ['/performance/live'] })
    expect(await screen.findByTestId('live-orders-empty')).toHaveTextContent('No live orders yet')
  })

  it('live orders table filters to execution_mode live only', async () => {
    mockLiveDashboardApis({
      activeStrategies: ['s1'],
      strategies: [
        createMockStrategyResponse({
          strategy_id: 's1',
          name: 'Strategy One',
          enabled: true,
          actual_state: 'RUNNING',
        }),
      ],
      ordersPerStrategy: [
        {
          strategyId: 's1',
          items: [
            createMockStrategyOrderItem({
              order_id: 'ord-1',
              execution_mode: 'live',
              status: 'FILLED',
              market_slug: 'btc-up',
            }),
          ],
        },
      ],
    })
    renderWithRouter({ initialEntries: ['/performance/live'] })
    expect(await screen.findByTestId('live-order-row-ord-1')).toBeInTheDocument()
    expect(screen.getByText('FILLED')).toBeInTheDocument()
  })
})
