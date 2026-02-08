import { screen } from '@testing-library/react'

import { renderWithRouter } from '@/test/utils'

describe('LiveTradingPage', () => {
  it('renders Live Trading title at /performance/live', async () => {
    renderWithRouter({ initialEntries: ['/performance/live'] })
    expect(
      await screen.findByRole('heading', { name: 'Live Trading', level: 1 }),
    ).toBeInTheDocument()
  })

  it('renders placeholder text at /performance/live', async () => {
    renderWithRouter({ initialEntries: ['/performance/live'] })
    expect(
      await screen.findByText(/Live trading dashboard — coming in next commit/),
    ).toBeInTheDocument()
  })
})
