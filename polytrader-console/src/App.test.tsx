import { screen, within } from '@testing-library/react'
import { vi } from 'vitest'
import App from './App'
import { marketApi } from './lib/api-client'
import { createMockMarket, createMockMarketsResponse } from './test/mocks'
import { mockAxiosResponse, renderWithQuery } from './test/utils'

const defaultedMarket = createMockMarket()

describe('App', () => {
  it('renders markets in a table with correct row count and cell content', async () => {
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

    const table = await screen.findByRole('table')
    const rows = within(table).getAllByRole('row')
    // Header row + 1 data row
    expect(rows).toHaveLength(2)

    const headerRow = rows[0]
    expect(headerRow).toHaveTextContent('Market')
    expect(headerRow).toHaveTextContent('Outcome')
    expect(headerRow).toHaveTextContent('Active')

    const dataRow = rows[1]
    expect(dataRow).toHaveTextContent(defaultedMarket.market_slug)
    expect(dataRow).toHaveTextContent(defaultedMarket.outcome)
    expect(dataRow).toHaveTextContent('Inactive') // active: false → Badge "Inactive"
  })

  it('renders empty state when no markets', async () => {
    vi.spyOn(marketApi, 'getMarketsApiV1MarketMarketsGet').mockResolvedValue(
      mockAxiosResponse({
        data: createMockMarketsResponse({ markets: [], count: 0 }),
      }),
    )
    renderWithQuery(<App />)
    await screen.findByRole('table')
    expect(screen.getByText('No results.')).toBeInTheDocument()
    const table = screen.getByRole('table')
    const rows = within(table).getAllByRole('row')
    // Header row + single "No results" row
    expect(rows).toHaveLength(2)
  })
})
