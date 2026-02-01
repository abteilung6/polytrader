import { screen, within } from '@testing-library/react'
import { vi } from 'vitest'

import { controlApi } from '@/lib/api-client'
import {
  createMockStrategyResponse,
  createMockStrategySignalItem,
  createMockStrategySignalsResponse,
  createMockStrategyOrderItem,
  createMockStrategyOrdersResponse,
  createMockClosedTradeItem,
  createMockPerformanceResponse,
  createMockPerformanceSummary,
} from '@/test/mocks'
import { mockAxiosResponse, renderWithRouter } from '@/test/utils'

const strategyId = 'strat-001'
const defaultStrategy = createMockStrategyResponse({ strategy_id: strategyId })

function mockStrategyDetail() {
  return vi
    .spyOn(controlApi, 'getStrategyByIdApiV1StateStrategiesStrategyIdGet')
    .mockResolvedValue(mockAxiosResponse({ data: defaultStrategy }))
}

function mockPerformanceEmpty() {
  return vi
    .spyOn(controlApi, 'getStrategyPerformanceApiV1StateStrategiesStrategyIdPerformanceGet')
    .mockResolvedValue(
      mockAxiosResponse({
        data: createMockPerformanceResponse({
          summary: createMockPerformanceSummary({
            total_realized_pnl: 0,
            total_trades: 0,
            win_rate_pct: null,
          }),
          items: [],
          next_cursor: null,
        }),
      }),
    )
}

describe('StrategyInstanceDetailPage', () => {
  beforeEach(() => {
    mockStrategyDetail()
  })

  describe('Signals tab', () => {
    beforeEach(() => {
      mockPerformanceEmpty()
    })

    it('renders signals table with expected columns when signals exist', async () => {
      const signal = createMockStrategySignalItem({
        event_id: 'evt-signal-1',
        market_slug: 'btc-updown-15m',
        rationale: 'Momentum signal',
        p_up: 0.65,
        p_down: 0.35,
      })
      vi.spyOn(
        controlApi,
        'getStrategySignalsApiV1StateStrategiesStrategyIdSignalsGet',
      ).mockResolvedValue(
        mockAxiosResponse({
          data: createMockStrategySignalsResponse({ items: [signal] }),
        }),
      )
      vi.spyOn(
        controlApi,
        'getStrategyOrdersApiV1StateStrategiesStrategyIdOrdersGet',
      ).mockResolvedValue(
        mockAxiosResponse({
          data: createMockStrategyOrdersResponse({ items: [] }),
        }),
      )

      renderWithRouter({
        initialEntries: [`/strategies/instances/${strategyId}`],
      })

      await screen.findByRole('tab', { name: 'Signals' })
      await screen.findByRole('tab', { name: 'Orders' })

      const table = await screen.findByRole('table')
      const rows = within(table).getAllByRole('row')
      expect(rows).toHaveLength(2)

      const headerRow = rows[0]
      expect(headerRow).toHaveTextContent('Market')
      expect(headerRow).toHaveTextContent('Rationale')

      const dataRow = rows[1]
      expect(dataRow).toHaveTextContent('btc-updown-15m')
      expect(dataRow).toHaveTextContent('Momentum signal')
      expect(dataRow).toHaveTextContent('65.00%')
      expect(dataRow).toHaveTextContent('35.00%')
    })

    it('renders empty state when no signals', async () => {
      vi.spyOn(
        controlApi,
        'getStrategySignalsApiV1StateStrategiesStrategyIdSignalsGet',
      ).mockResolvedValue(
        mockAxiosResponse({
          data: createMockStrategySignalsResponse({ items: [] }),
        }),
      )
      vi.spyOn(
        controlApi,
        'getStrategyOrdersApiV1StateStrategiesStrategyIdOrdersGet',
      ).mockResolvedValue(
        mockAxiosResponse({
          data: createMockStrategyOrdersResponse({ items: [] }),
        }),
      )

      renderWithRouter({
        initialEntries: [`/strategies/instances/${strategyId}`],
      })

      await screen.findByRole('tab', { name: 'Signals' })
      expect(await screen.findByText('No results.')).toBeInTheDocument()
    })
  })

  describe('Orders tab', () => {
    beforeEach(() => {
      mockPerformanceEmpty()
    })

    it('renders orders table with expected columns when orders exist', async () => {
      const order = createMockStrategyOrderItem({
        order_id: 'ord-001',
        client_order_id: 'client-001',
        market_slug: 'btc-updown-15m',
        side: 'BUY',
        size: 100,
        limit_price: 0.45,
        status: 'LIVE',
        execution_mode: 'paper',
      })
      vi.spyOn(
        controlApi,
        'getStrategySignalsApiV1StateStrategiesStrategyIdSignalsGet',
      ).mockResolvedValue(
        mockAxiosResponse({
          data: createMockStrategySignalsResponse({ items: [] }),
        }),
      )
      vi.spyOn(
        controlApi,
        'getStrategyOrdersApiV1StateStrategiesStrategyIdOrdersGet',
      ).mockResolvedValue(
        mockAxiosResponse({
          data: createMockStrategyOrdersResponse({ items: [order] }),
        }),
      )

      renderWithRouter({
        initialEntries: [`/strategies/instances/${strategyId}?tab=orders`],
      })

      await screen.findByRole('tab', { name: 'Orders' })

      const table = await screen.findByRole('table')
      const rows = within(table).getAllByRole('row')
      expect(rows).toHaveLength(2)

      const headerRow = rows[0]
      expect(headerRow).toHaveTextContent('Market')
      expect(headerRow).toHaveTextContent('Side')
      expect(headerRow).toHaveTextContent('Status')

      const dataRow = rows[1]
      expect(dataRow).toHaveTextContent('btc-updown-15m')
      expect(dataRow).toHaveTextContent('BUY')
      expect(dataRow).toHaveTextContent('LIVE')
      expect(dataRow).toHaveTextContent('Paper')
    })

    it('renders empty state when no orders', async () => {
      vi.spyOn(
        controlApi,
        'getStrategySignalsApiV1StateStrategiesStrategyIdSignalsGet',
      ).mockResolvedValue(
        mockAxiosResponse({
          data: createMockStrategySignalsResponse({ items: [] }),
        }),
      )
      vi.spyOn(
        controlApi,
        'getStrategyOrdersApiV1StateStrategiesStrategyIdOrdersGet',
      ).mockResolvedValue(
        mockAxiosResponse({
          data: createMockStrategyOrdersResponse({ items: [] }),
        }),
      )

      renderWithRouter({
        initialEntries: [`/strategies/instances/${strategyId}?tab=orders`],
      })

      await screen.findByRole('tab', { name: 'Orders' })
      expect(await screen.findByText('No results.')).toBeInTheDocument()
    })
  })

  describe('Past Performance tab', () => {
    it('renders Past Performance tab and empty state when no closed trades', async () => {
      vi.spyOn(
        controlApi,
        'getStrategySignalsApiV1StateStrategiesStrategyIdSignalsGet',
      ).mockResolvedValue(
        mockAxiosResponse({
          data: createMockStrategySignalsResponse({ items: [] }),
        }),
      )
      vi.spyOn(
        controlApi,
        'getStrategyOrdersApiV1StateStrategiesStrategyIdOrdersGet',
      ).mockResolvedValue(
        mockAxiosResponse({
          data: createMockStrategyOrdersResponse({ items: [] }),
        }),
      )
      mockPerformanceEmpty()

      renderWithRouter({
        initialEntries: [`/strategies/instances/${strategyId}?tab=performance`],
      })

      await screen.findByRole('tab', { name: 'Past Performance' })
      expect(screen.getByRole('tab', { name: 'Signals' })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: 'Orders' })).toBeInTheDocument()

      expect(
        await screen.findByText(
          'No closed trades yet. Performance will appear here after positions are closed.',
        ),
      ).toBeInTheDocument()
      expect(screen.getByText('Total realized P&L')).toBeInTheDocument()
      expect(screen.getByText('Total trades')).toBeInTheDocument()
      expect(screen.getByText('Win rate')).toBeInTheDocument()
    })

    it('renders performance summary and table when closed trades exist', async () => {
      const trade = createMockClosedTradeItem({
        market_slug: 'btc-updown-15m',
        outcome: 'UP',
        pnl: 15.5,
        pnl_pct: 25.0,
        result: 'WIN',
        execution_mode: 'paper',
      })
      vi.spyOn(
        controlApi,
        'getStrategySignalsApiV1StateStrategiesStrategyIdSignalsGet',
      ).mockResolvedValue(
        mockAxiosResponse({
          data: createMockStrategySignalsResponse({ items: [] }),
        }),
      )
      vi.spyOn(
        controlApi,
        'getStrategyOrdersApiV1StateStrategiesStrategyIdOrdersGet',
      ).mockResolvedValue(
        mockAxiosResponse({
          data: createMockStrategyOrdersResponse({ items: [] }),
        }),
      )
      vi.spyOn(
        controlApi,
        'getStrategyPerformanceApiV1StateStrategiesStrategyIdPerformanceGet',
      ).mockResolvedValue(
        mockAxiosResponse({
          data: createMockPerformanceResponse({
            summary: createMockPerformanceSummary({
              total_realized_pnl: 15.5,
              total_trades: 1,
              win_rate_pct: 100,
            }),
            items: [trade],
            next_cursor: null,
          }),
        }),
      )

      renderWithRouter({
        initialEntries: [`/strategies/instances/${strategyId}?tab=performance`],
      })

      await screen.findByRole('tab', { name: 'Past Performance' })

      expect(await screen.findByText('15.50 USD')).toBeInTheDocument()
      expect(screen.getByText('1')).toBeInTheDocument()
      expect(screen.getByText('100.0%')).toBeInTheDocument()

      const table = screen.getByRole('table')
      const rows = within(table).getAllByRole('row')
      expect(rows).toHaveLength(2)
      const headerRow = rows[0]
      expect(headerRow).toHaveTextContent('Market')
      expect(headerRow).toHaveTextContent('P&L (USD)')
      expect(headerRow).toHaveTextContent('Result')
      const dataRow = rows[1]
      expect(dataRow).toHaveTextContent('btc-updown-15m')
      expect(dataRow).toHaveTextContent('15.50')
      expect(dataRow).toHaveTextContent('WIN')
      expect(dataRow).toHaveTextContent('Paper')
    })
  })
})
