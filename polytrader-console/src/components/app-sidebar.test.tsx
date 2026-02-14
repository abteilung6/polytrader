import { screen } from '@testing-library/react'

import { renderWithRouter } from '@/test/utils'

/**
 * Sidebar is rendered inside the layout. Test navigation structure by
 * rendering a layout route (markets avoids Control-page API mocks) and
 * asserting on sidebar links.
 */
describe('AppSidebar — Performance navigation', () => {
  it('renders collapsible Performance group with Live Trading and Paper Trading sub-items', async () => {
    renderWithRouter({ initialEntries: ['/markets'] })
    const liveLink = await screen.findByRole('link', { name: /Live Trading/i })
    expect(liveLink).toHaveAttribute('href', '/performance/live')

    const paperLink = screen.getByRole('link', { name: /Paper Trading/i })
    expect(paperLink).toHaveAttribute('href', '/performance/paper')
  })

  it('renders Control link to /control', async () => {
    renderWithRouter({ initialEntries: ['/markets'] })
    const controlLink = await screen.findByRole('link', { name: /Control/i })
    expect(controlLink).toHaveAttribute('href', '/control')
  })
})
