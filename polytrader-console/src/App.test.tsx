import { screen } from '@testing-library/react'
import { vi } from 'vitest'
import App from './App'
import { marketApi } from './lib/api-client'
import { createMockMarket, createMockMarketsResponse } from './test/mocks'
import { mockAxiosResponse, renderWithQuery } from './test/utils'

const defaultedMarket = createMockMarket()

describe('App', () => {
  const customRender = async () => {
    vi.spyOn(marketApi, 'getMarketsApiV1MarketMarketsGet').mockResolvedValue(
      mockAxiosResponse({
        data: createMockMarketsResponse({
          markets: [defaultedMarket],
          count: 1,
        }),
      }),
    )
    renderWithQuery(<App />)
    screen.getByText('Loading…')
    await screen.findByText(/"count":\s*1/)
  }

  it('renders markets', async () => {
    await customRender()
    screen.getByText(new RegExp(defaultedMarket.market_slug))
    screen.getByText(new RegExp(defaultedMarket.outcome))
  })
})
