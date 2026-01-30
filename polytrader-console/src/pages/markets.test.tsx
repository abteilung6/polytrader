import { screen, within } from '@testing-library/react'
import { vi } from 'vitest'
import { marketApi } from '@/lib/api-client'
import { createMockMarket, createMockMarketsResponse } from '@/test/mocks'
import { mockAxiosResponse, renderWithRouter } from '@/test/utils'

const defaultedMarket = createMockMarket()

describe('MarketsPage', () => {
  it('renders markets in a table with correct row count and cell content', async () => {
    vi.spyOn(marketApi, 'getMarketsApiV1MarketMarketsGet').mockResolvedValue(
      mockAxiosResponse({
        data: createMockMarketsResponse({
          markets: [defaultedMarket],
          count: 1,
        }),
      }),
    )
    renderWithRouter({ initialEntries: ['/markets'] })
    await screen.findByText('Loading…')

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

  it('slug cell links to market detail and detail page shows slug', async () => {
    vi.spyOn(marketApi, 'getMarketsApiV1MarketMarketsGet').mockResolvedValue(
      mockAxiosResponse({
        data: createMockMarketsResponse({
          markets: [defaultedMarket],
          count: 1,
        }),
      }),
    )
    renderWithRouter({ initialEntries: ['/markets'] })
    await screen.findByText('Loading…')
    const table = await screen.findByRole('table')
    const slugLink = within(table).getByRole('link', { name: defaultedMarket.market_slug })
    expect(slugLink).toHaveAttribute('href', `/markets/${defaultedMarket.market_slug}`)
  })

  it('market detail page shows slug when navigated to directly', async () => {
    renderWithRouter({
      initialEntries: [`/markets/${defaultedMarket.market_slug}`],
    })
    expect(
      await screen.findByText(new RegExp(`Market:\\s*${defaultedMarket.market_slug}`)),
    ).toBeInTheDocument()
  })

  it('renders empty state when no markets', async () => {
    vi.spyOn(marketApi, 'getMarketsApiV1MarketMarketsGet').mockResolvedValue(
      mockAxiosResponse({
        data: createMockMarketsResponse({ markets: [], count: 0 }),
      }),
    )
    renderWithRouter({ initialEntries: ['/markets'] })
    await screen.findByRole('table')
    expect(screen.getByText('No results.')).toBeInTheDocument()
    const table = screen.getByRole('table')
    const rows = within(table).getAllByRole('row')
    // Header row + single "No results" row
    expect(rows).toHaveLength(2)
  })
})
