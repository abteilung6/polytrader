import { screen, within } from '@testing-library/react'
import { vi } from 'vitest'

import { controlApi } from '@/lib/api-client'
import { createMockStrategyResponse, createMockStrategiesResponse } from '@/test/mocks'
import { mockAxiosResponse, renderWithRouter } from '@/test/utils'

const defaultInstance = createMockStrategyResponse()

describe('StrategiesInstancesPage', () => {
  it('renders strategy instances in a table with expected columns', async () => {
    vi.spyOn(controlApi, 'getStrategiesApiV1StateStrategiesGet').mockResolvedValue(
      mockAxiosResponse({
        data: createMockStrategiesResponse({
          strategies: [defaultInstance],
        }),
      }),
    )
    renderWithRouter({ initialEntries: ['/strategies/instances'] })
    await screen.findByText('Loading…')

    const table = await screen.findByRole('table')
    const rows = within(table).getAllByRole('row')
    expect(rows).toHaveLength(2)

    const headerRow = rows[0]
    expect(headerRow).toHaveTextContent('Strategy ID')
    expect(headerRow).toHaveTextContent('Name')
    expect(headerRow).toHaveTextContent('Template type ID')
    expect(headerRow).toHaveTextContent('Template version')
    expect(headerRow).toHaveTextContent('Actual state')
    expect(headerRow).toHaveTextContent('Created at')

    const dataRow = rows[1]
    expect(dataRow).toHaveTextContent(defaultInstance.strategy_id)
    expect(dataRow).toHaveTextContent(defaultInstance.name)
    expect(dataRow).toHaveTextContent(defaultInstance.template_type_id)
    expect(dataRow).toHaveTextContent(defaultInstance.template_version)
    expect(dataRow).toHaveTextContent(defaultInstance.actual_state)

    const nameLink = within(dataRow).getByRole('link', { name: defaultInstance.name })
    expect(nameLink).toHaveAttribute('href', `/strategies/instances/${defaultInstance.strategy_id}`)
  })

  it('renders empty state when no instances', async () => {
    vi.spyOn(controlApi, 'getStrategiesApiV1StateStrategiesGet').mockResolvedValue(
      mockAxiosResponse({
        data: createMockStrategiesResponse({ strategies: [] }),
      }),
    )
    renderWithRouter({ initialEntries: ['/strategies/instances'] })
    await screen.findByRole('table')
    expect(screen.getByText('No results.')).toBeInTheDocument()
    const table = screen.getByRole('table')
    const rows = within(table).getAllByRole('row')
    expect(rows).toHaveLength(2)
  })
})
