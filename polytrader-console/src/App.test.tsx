import { screen } from '@testing-library/react'
import { vi } from 'vitest'
import App from './App'
import { marketApi } from './lib/api-client'
import { createMockMarket, createMockMarketsResponse } from './test/mocks'
import { mockAxiosResponse, renderWithQuery } from './test/utils'

const defaultedMarket = createMockMarket()

describe('App', () => {
  it('renders markets in a table', async () => {
    vi.spyOn(marketApi, 'getMarketsApiV1MarketMarketsGet').mockResolvedValue(
      mockAxiosResponse({
        data: createMockMarketsResponse({
          markets: [defaultedMarket],
          count: 1,
        }),
      }),
    )
    renderWithQuery(<App />)
    expect(screen.getByText('Loading…')).toBeInTheDocument()
    await screen.findByRole('table')
    expect(screen.getByText(defaultedMarket.market_slug)).toBeInTheDocument()
    expect(screen.getByText(defaultedMarket.outcome)).toBeInTheDocument()
  })
})
