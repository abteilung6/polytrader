import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

import { controlApi } from '@/lib/api-client'
import type { LiveStrategiesResponse, StrategiesResponse, StrategyResponse } from '@/lib/api'
import { mockAxiosResponse, renderWithQuery, renderWithQueryAndRouter } from '@/test/utils'

import { ActiveStrategiesPanel } from './active-strategies-panel'

function makeStrategy(overrides: Partial<StrategyResponse> = {}): StrategyResponse {
  return {
    strategy_id: 'strat-001',
    name: 'Test Strategy',
    description: null,
    config: {},
    template_type_id: 'simple_threshold',
    template_version: '1.0.0',
    desired_state: 'RUNNING',
    actual_state: 'RUNNING',
    last_transition_at: '2026-02-08T12:00:00Z',
    last_error: null,
    run_identity: null,
    deployment_id: null,
    run_id: null,
    created_at: '2026-02-01T00:00:00Z',
    updated_at: '2026-02-08T12:00:00Z',
    enabled: true,
    ...overrides,
  }
}

function mockLiveStrategies(ids: string[]) {
  vi.spyOn(controlApi, 'getLiveStrategiesApiV1StateLiveStrategiesGet').mockResolvedValue(
    mockAxiosResponse({ data: { active_strategies: ids } as LiveStrategiesResponse }),
  )
}

function mockInstances(strategies: StrategyResponse[]) {
  vi.spyOn(controlApi, 'getStrategiesApiV1StateStrategiesGet').mockResolvedValue(
    mockAxiosResponse({ data: { strategies } as StrategiesResponse }),
  )
}

describe('ActiveStrategiesPanel', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders panel card', async () => {
    mockLiveStrategies([])
    mockInstances([])

    renderWithQueryAndRouter(<ActiveStrategiesPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('active-strategies-panel')).toBeInTheDocument()
    })
    expect(screen.getByText('Active Live Strategies')).toBeInTheDocument()
  })

  it('shows empty state when no live strategies', async () => {
    mockLiveStrategies([])
    mockInstances([])

    renderWithQueryAndRouter(<ActiveStrategiesPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('active-strategies-empty')).toBeInTheDocument()
    })
    expect(screen.getByTestId('active-strategies-empty')).toHaveTextContent(
      'No strategies activated for live trading',
    )
  })

  it('shows count badge with 0 when empty', async () => {
    mockLiveStrategies([])
    mockInstances([])

    renderWithQueryAndRouter(<ActiveStrategiesPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('active-count-badge')).toHaveTextContent('0')
    })
  })

  it('displays matched strategy with name and template', async () => {
    const strat = makeStrategy({
      strategy_id: 'strat-001',
      name: 'Alpha Momentum',
      template_type_id: 'momentum',
      template_version: '2.0.0',
    })

    mockLiveStrategies(['strat-001'])
    mockInstances([strat])

    renderWithQueryAndRouter(<ActiveStrategiesPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('active-strategy-strat-001')).toBeInTheDocument()
    })
    expect(screen.getByText('Alpha Momentum')).toBeInTheDocument()
    expect(screen.getByText('momentum v2.0.0')).toBeInTheDocument()
  })

  it('shows correct count badge for multiple strategies', async () => {
    const strats = [
      makeStrategy({ strategy_id: 'strat-001', name: 'Alpha A' }),
      makeStrategy({ strategy_id: 'strat-002', name: 'Alpha B' }),
    ]

    mockLiveStrategies(['strat-001', 'strat-002'])
    mockInstances(strats)

    renderWithQueryAndRouter(<ActiveStrategiesPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('active-count-badge')).toHaveTextContent('2')
    })
    expect(screen.getByTestId('active-strategy-strat-001')).toBeInTheDocument()
    expect(screen.getByTestId('active-strategy-strat-002')).toBeInTheDocument()
  })

  it('shows state badge (RUNNING)', async () => {
    mockLiveStrategies(['strat-001'])
    mockInstances([makeStrategy({ strategy_id: 'strat-001', actual_state: 'RUNNING' })])

    renderWithQueryAndRouter(<ActiveStrategiesPanel />)

    await waitFor(() => {
      expect(screen.getByText('RUNNING')).toBeInTheDocument()
    })
  })

  it('shows loading skeletons', () => {
    vi.spyOn(controlApi, 'getLiveStrategiesApiV1StateLiveStrategiesGet').mockReturnValue(
      new Promise(() => {}),
    )
    vi.spyOn(controlApi, 'getStrategiesApiV1StateStrategiesGet').mockReturnValue(
      new Promise(() => {}),
    )

    // No Link rendered in loading state, so renderWithQuery suffices
    renderWithQuery(<ActiveStrategiesPanel />)

    expect(screen.getByTestId('active-strategies-loading')).toBeInTheDocument()
  })

  it('shows orphan message when IDs cannot be matched', async () => {
    mockLiveStrategies(['strat-001', 'strat-999'])
    mockInstances([makeStrategy({ strategy_id: 'strat-001' })])

    renderWithQueryAndRouter(<ActiveStrategiesPanel />)

    await waitFor(() => {
      expect(screen.getByText(/1 activated strategy ID\(s\) not found/)).toBeInTheDocument()
    })
  })

  it('does not show pagination when 5 or fewer strategies', async () => {
    const ids = Array.from({ length: 3 }, (_, i) => `strat-${i}`)
    const strats = ids.map((id) => makeStrategy({ strategy_id: id, name: `S ${id}` }))

    mockLiveStrategies(ids)
    mockInstances(strats)

    renderWithQueryAndRouter(<ActiveStrategiesPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('active-count-badge')).toHaveTextContent('3')
    })
    expect(screen.queryByTestId('active-strategies-pagination')).not.toBeInTheDocument()
  })

  it('shows pagination when more than 5 strategies', async () => {
    const ids = Array.from({ length: 8 }, (_, i) => `strat-${i}`)
    const strats = ids.map((id) => makeStrategy({ strategy_id: id, name: `S ${id}` }))

    mockLiveStrategies(ids)
    mockInstances(strats)

    renderWithQueryAndRouter(<ActiveStrategiesPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('active-strategies-pagination')).toBeInTheDocument()
    })
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument()
    // First page: 5 rows, not all 8
    expect(screen.getByTestId('active-strategy-strat-0')).toBeInTheDocument()
    expect(screen.getByTestId('active-strategy-strat-4')).toBeInTheDocument()
    expect(screen.queryByTestId('active-strategy-strat-5')).not.toBeInTheDocument()
  })

  it('shows card dropdown with Deactivate all when strategies are active', async () => {
    const user = userEvent.setup()
    mockLiveStrategies(['strat-001'])
    mockInstances([makeStrategy({ strategy_id: 'strat-001', name: 'Alpha' })])

    renderWithQueryAndRouter(<ActiveStrategiesPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('active-strategies-card-actions')).toBeInTheDocument()
    })
    await user.click(screen.getByTestId('active-strategies-card-actions'))
    expect(screen.getByTestId('active-strategies-deactivate-all')).toHaveTextContent(
      'Deactivate all',
    )
  })

  it('does not show card dropdown when no active strategies', async () => {
    mockLiveStrategies([])
    mockInstances([])

    renderWithQueryAndRouter(<ActiveStrategiesPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('active-strategies-empty')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('active-strategies-card-actions')).not.toBeInTheDocument()
  })

  it('Deactivate all opens confirmation dialog', async () => {
    const user = userEvent.setup()
    mockLiveStrategies(['strat-001'])
    mockInstances([makeStrategy({ strategy_id: 'strat-001', name: 'Alpha' })])

    renderWithQueryAndRouter(<ActiveStrategiesPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('active-strategies-card-actions')).toBeInTheDocument()
    })
    await user.click(screen.getByTestId('active-strategies-card-actions'))
    await user.click(screen.getByTestId('active-strategies-deactivate-all'))

    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent('Deactivate all live strategies')
    expect(dialog).toHaveTextContent('Remove all 1 strategy(ies) from the live pool')
  })

  it('shows Remove from active in row dropdown and opens confirmation dialog', async () => {
    const user = userEvent.setup()
    mockLiveStrategies(['strat-001'])
    mockInstances([makeStrategy({ strategy_id: 'strat-001', name: 'Alpha Momentum' })])

    renderWithQueryAndRouter(<ActiveStrategiesPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('active-strategy-strat-001')).toBeInTheDocument()
    })

    const actionsButton = screen.getByTestId('active-strategy-actions-strat-001')
    await user.click(actionsButton)
    const removeItem = screen.getByTestId('active-strategy-remove')
    expect(removeItem).toHaveTextContent('Remove from active')
    await user.click(removeItem)

    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent('Remove from active live strategies')
    expect(dialog).toHaveTextContent('Alpha Momentum')
  })

  it('navigates to next and previous pages', async () => {
    const user = userEvent.setup()
    const ids = Array.from({ length: 8 }, (_, i) => `strat-${i}`)
    const strats = ids.map((id) => makeStrategy({ strategy_id: id, name: `S ${id}` }))

    mockLiveStrategies(ids)
    mockInstances(strats)

    renderWithQueryAndRouter(<ActiveStrategiesPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('active-strategies-pagination')).toBeInTheDocument()
    })

    // Previous should be disabled on page 1
    expect(screen.getByTestId('pagination-prev')).toBeDisabled()

    // Click next
    await user.click(screen.getByTestId('pagination-next'))
    expect(screen.getByText('Page 2 of 2')).toBeInTheDocument()
    expect(screen.getByTestId('active-strategy-strat-5')).toBeInTheDocument()
    expect(screen.getByTestId('active-strategy-strat-7')).toBeInTheDocument()
    expect(screen.queryByTestId('active-strategy-strat-0')).not.toBeInTheDocument()

    // Next should be disabled on last page
    expect(screen.getByTestId('pagination-next')).toBeDisabled()

    // Click previous
    await user.click(screen.getByTestId('pagination-prev'))
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument()
    expect(screen.getByTestId('active-strategy-strat-0')).toBeInTheDocument()
  })
})
