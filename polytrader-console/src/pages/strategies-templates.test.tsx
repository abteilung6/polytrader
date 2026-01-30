import { screen, within } from '@testing-library/react'
import { vi } from 'vitest'

import { controlApi } from '@/lib/api-client'
import { createMockStrategyType, createMockStrategyTypesResponse } from '@/test/mocks'
import { mockAxiosResponse, renderWithRouter } from '@/test/utils'

const defaultTemplate = createMockStrategyType()

describe('StrategiesTemplatesPage', () => {
  it('renders strategy templates in a table with type_id, name, and latest version', async () => {
    vi.spyOn(controlApi, 'listStrategyTemplatesApiV1StateStrategiesTemplatesGet').mockResolvedValue(
      mockAxiosResponse({
        data: createMockStrategyTypesResponse({
          types: [defaultTemplate],
        }),
      }),
    )
    renderWithRouter({ initialEntries: ['/strategies/templates'] })
    await screen.findByText('Loading…')

    const table = await screen.findByRole('table')
    const rows = within(table).getAllByRole('row')
    expect(rows).toHaveLength(2)

    const headerRow = rows[0]
    expect(headerRow).toHaveTextContent('Type ID')
    expect(headerRow).toHaveTextContent('Name')
    expect(headerRow).toHaveTextContent('Latest version')

    const dataRow = rows[1]
    expect(dataRow).toHaveTextContent(defaultTemplate.type_id)
    expect(dataRow).toHaveTextContent(defaultTemplate.name)
    expect(dataRow).toHaveTextContent('1.1.0')
  })

  it('renders empty state when no templates', async () => {
    vi.spyOn(controlApi, 'listStrategyTemplatesApiV1StateStrategiesTemplatesGet').mockResolvedValue(
      mockAxiosResponse({
        data: createMockStrategyTypesResponse({ types: [] }),
      }),
    )
    renderWithRouter({ initialEntries: ['/strategies/templates'] })
    await screen.findByRole('table')
    expect(screen.getByText('No results.')).toBeInTheDocument()
    const table = screen.getByRole('table')
    const rows = within(table).getAllByRole('row')
    expect(rows).toHaveLength(2)
  })

  it('latest version shows — when available_versions is empty', async () => {
    vi.spyOn(controlApi, 'listStrategyTemplatesApiV1StateStrategiesTemplatesGet').mockResolvedValue(
      mockAxiosResponse({
        data: createMockStrategyTypesResponse({
          types: [createMockStrategyType({ available_versions: [] })],
        }),
      }),
    )
    renderWithRouter({ initialEntries: ['/strategies/templates'] })
    const table = await screen.findByRole('table')
    const dataRow = within(table).getAllByRole('row')[1]
    expect(dataRow).toHaveTextContent('—')
  })
})
