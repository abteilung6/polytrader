import { screen, within } from '@testing-library/react'
import { vi } from 'vitest'

import { controlApi } from '@/lib/api-client'
import {
  createMockStrategyResponse,
  createMockStrategySignalItem,
  createMockStrategySignalsResponse,
  createMockStrategyOrderItem,
  createMockStrategyOrdersResponse,
} from '@/test/mocks'
import { mockAxiosResponse, renderWithRouter } from '@/test/utils'

const strategyId = 'strat-001'
const defaultStrategy = createMockStrategyResponse({ strategy_id: strategyId })

function mockStrategyDetail() {
  return vi
    .spyOn(controlApi, 'getStrategyByIdApiV1StateStrategiesStrategyIdGet')
    .mockResolvedValue(mockAxiosResponse({ data: defaultStrategy }))
}

describe('StrategyInstanceDetailPage', () => {
  beforeEach(() => {
    mockStrategyDetail()
  })

  describe('Signals tab', () => {
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
      expect(headerRow).toHaveTextContent('Event ID')
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
      expect(headerRow).toHaveTextContent('Order ID')
      expect(headerRow).toHaveTextContent('Client order ID')
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
})
