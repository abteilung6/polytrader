import { screen, within } from '@testing-library/react'
import { vi } from 'vitest'

import { controlApi } from '@/lib/api-client'
import {
  createMockPerformanceOverviewItem,
  createMockPerformanceOverviewResponse,
} from '@/test/mocks'
import { mockAxiosResponse, renderWithRouter } from '@/test/utils'

const defaultItem = createMockPerformanceOverviewItem()

describe('PerformancePage', () => {
  it('redirects /performance to /performance/paper and shows Performance Overview', async () => {
    vi.spyOn(
      controlApi,
      'getPerformanceOverviewApiV1StateStrategiesPerformanceOverviewGet',
    ).mockResolvedValue(
      mockAxiosResponse({
        data: createMockPerformanceOverviewResponse({ items: [] }),
      }),
    )
    renderWithRouter({ initialEntries: ['/performance'] })
    expect(await screen.findByText('Performance Overview')).toBeInTheDocument()
  })

  it('renders Performance Overview when navigated to /performance/paper', async () => {
    vi.spyOn(
      controlApi,
      'getPerformanceOverviewApiV1StateStrategiesPerformanceOverviewGet',
    ).mockResolvedValue(
      mockAxiosResponse({
        data: createMockPerformanceOverviewResponse({ items: [] }),
      }),
    )
    renderWithRouter({ initialEntries: ['/performance/paper'] })
    expect(await screen.findByText('Performance Overview')).toBeInTheDocument()
  })

  it('renders window selector with all preset tabs', async () => {
    vi.spyOn(
      controlApi,
      'getPerformanceOverviewApiV1StateStrategiesPerformanceOverviewGet',
    ).mockResolvedValue(
      mockAxiosResponse({
        data: createMockPerformanceOverviewResponse({ items: [] }),
      }),
    )
    renderWithRouter({ initialEntries: ['/performance/paper'] })
    await screen.findByText('Performance Overview')

    expect(screen.getByRole('tab', { name: '1d' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '3d' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '7d' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'All' })).toBeInTheDocument()
  })

  it('defaults to "1d" window with "Since" label', async () => {
    vi.spyOn(
      controlApi,
      'getPerformanceOverviewApiV1StateStrategiesPerformanceOverviewGet',
    ).mockResolvedValue(
      mockAxiosResponse({
        data: createMockPerformanceOverviewResponse({ items: [] }),
      }),
    )
    renderWithRouter({ initialEntries: ['/performance/paper'] })
    await screen.findByText('Performance Overview')

    const tab1d = screen.getByRole('tab', { name: '1d' })
    expect(tab1d).toHaveAttribute('data-state', 'active')
    expect(screen.getByText(/Since /)).toBeInTheDocument()
  })

  it('renders performance data in a table with key columns', async () => {
    vi.spyOn(
      controlApi,
      'getPerformanceOverviewApiV1StateStrategiesPerformanceOverviewGet',
    ).mockResolvedValue(
      mockAxiosResponse({
        data: createMockPerformanceOverviewResponse({
          items: [defaultItem],
        }),
      }),
    )
    renderWithRouter({ initialEntries: ['/performance/paper'] })

    // Wait for the strategy name to appear (data loaded into table)
    expect(await screen.findByText(defaultItem.name)).toBeInTheDocument()

    const table = screen.getByRole('table')
    const rows = within(table).getAllByRole('row')
    // 1 header + 1 data row
    expect(rows).toHaveLength(2)

    const dataRow = rows[1]
    expect(dataRow).toHaveTextContent(defaultItem.name)
    expect(dataRow).toHaveTextContent(String(defaultItem.trade_count))
    expect(dataRow).toHaveTextContent(String(defaultItem.wins))
    expect(dataRow).toHaveTextContent(String(defaultItem.losses))
  })

  it('renders "No results." when API returns empty items', async () => {
    vi.spyOn(
      controlApi,
      'getPerformanceOverviewApiV1StateStrategiesPerformanceOverviewGet',
    ).mockResolvedValue(
      mockAxiosResponse({
        data: createMockPerformanceOverviewResponse({ items: [] }),
      }),
    )
    renderWithRouter({ initialEntries: ['/performance/paper'] })
    await screen.findByRole('table')
    expect(screen.getByText('No results.')).toBeInTheDocument()
  })

  it('renders loading state', async () => {
    vi.spyOn(
      controlApi,
      'getPerformanceOverviewApiV1StateStrategiesPerformanceOverviewGet',
    ).mockReturnValue(new Promise(() => {}))
    renderWithRouter({ initialEntries: ['/performance/paper'] })
    expect(await screen.findByText('Loading…')).toBeInTheDocument()
  })

  it('renders error state', async () => {
    vi.spyOn(
      controlApi,
      'getPerformanceOverviewApiV1StateStrategiesPerformanceOverviewGet',
    ).mockRejectedValue(new Error('Network error'))
    renderWithRouter({ initialEntries: ['/performance/paper'] })
    expect(await screen.findByText(/Error: Network error/)).toBeInTheDocument()
  })
})
