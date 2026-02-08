/**
 * Tests for strategy instance table columns — Mode column and expanded
 * actions dropdown per PILOT_LIVE.md Commit 8.
 *
 * Covers:
 * - Mode column badge (LIVE/PAPER) based on enabled field
 * - Start visible only when STOPPED/ERROR, calls mutation directly
 * - Stop visible only when RUNNING/STARTING, opens standard confirmation
 * - Add to active strategies visible when not enabled, opens typed confirmation
 * - Remove from active visible when enabled, opens standard confirmation
 * - Dropdown shows correct actions based on state + enabled
 */
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, type Mock } from 'vitest'

import { controlApi } from '@/lib/api-client'
import type { CommandEnvelopeResponse } from '@/lib/api'
import { createMockStrategyResponse, createMockStrategiesResponse } from '@/test/mocks'
import { mockAxiosResponse, renderWithRouter } from '@/test/utils'

const mockCommandResponse: CommandEnvelopeResponse = {
  command_id: '00000000-0000-0000-0000-000000000001',
  status: 'applied',
  submitted_at: '2026-02-08T12:00:00Z',
}

/** Helper: render strategies page with given strategy instances. */
function renderWithStrategies(strategies: ReturnType<typeof createMockStrategyResponse>[]) {
  vi.spyOn(controlApi, 'getStrategiesApiV1StateStrategiesGet').mockResolvedValue(
    mockAxiosResponse({
      data: createMockStrategiesResponse({ strategies }),
    }),
  )
  return renderWithRouter({ initialEntries: ['/strategies/instances'] })
}

/** Helper: open the actions dropdown for the first row's actions button. */
async function openActionsDropdown() {
  const user = userEvent.setup()
  const btn = await screen.findByRole('button', { name: 'Open actions menu' })
  await user.click(btn)
}

describe('StrategyInstanceColumns — Mode column', () => {
  it('shows LIVE badge when strategy.enabled is true', async () => {
    renderWithStrategies([
      createMockStrategyResponse({
        strategy_id: 'live-strat',
        enabled: true,
        actual_state: 'RUNNING',
      }),
    ])

    const badge = await screen.findByTestId('mode-badge-live-strat')
    expect(badge).toHaveTextContent('LIVE')
  })

  it('shows PAPER badge when strategy.enabled is false', async () => {
    renderWithStrategies([
      createMockStrategyResponse({
        strategy_id: 'paper-strat',
        enabled: false,
        actual_state: 'RUNNING',
      }),
    ])

    const badge = await screen.findByTestId('mode-badge-paper-strat')
    expect(badge).toHaveTextContent('PAPER')
  })

  it('renders Mode column header', async () => {
    renderWithStrategies([createMockStrategyResponse()])

    const table = await screen.findByRole('table')
    const headerRow = within(table).getAllByRole('row')[0]
    expect(headerRow).toHaveTextContent('Mode')
  })
})

describe('StrategyInstanceColumns — Dropdown lifecycle actions', () => {
  it('shows Start when actual_state is STOPPED', async () => {
    renderWithStrategies([createMockStrategyResponse({ actual_state: 'STOPPED', enabled: false })])

    await openActionsDropdown()

    expect(screen.getByTestId('action-start')).toHaveTextContent('Start')
    expect(screen.queryByTestId('action-stop')).not.toBeInTheDocument()
  })

  it('shows Start when actual_state is ERROR', async () => {
    renderWithStrategies([createMockStrategyResponse({ actual_state: 'ERROR', enabled: false })])

    await openActionsDropdown()

    expect(screen.getByTestId('action-start')).toHaveTextContent('Start')
    expect(screen.queryByTestId('action-stop')).not.toBeInTheDocument()
  })

  it('shows Stop when actual_state is RUNNING', async () => {
    renderWithStrategies([createMockStrategyResponse({ actual_state: 'RUNNING', enabled: false })])

    await openActionsDropdown()

    expect(screen.getByTestId('action-stop')).toHaveTextContent('Stop')
    expect(screen.queryByTestId('action-start')).not.toBeInTheDocument()
  })

  it('shows Stop when actual_state is STARTING', async () => {
    renderWithStrategies([createMockStrategyResponse({ actual_state: 'STARTING', enabled: false })])

    await openActionsDropdown()

    expect(screen.getByTestId('action-stop')).toHaveTextContent('Stop')
    expect(screen.queryByTestId('action-start')).not.toBeInTheDocument()
  })

  it('Start calls mutation directly without confirmation dialog', async () => {
    const spy = vi
      .spyOn(controlApi, 'updateStrategyApiV1CommandsStrategiesStrategyIdPatch')
      .mockResolvedValue(
        mockAxiosResponse({ data: createMockStrategyResponse({ actual_state: 'STARTING' }) }),
      )

    renderWithStrategies([createMockStrategyResponse({ actual_state: 'STOPPED', enabled: false })])

    await openActionsDropdown()

    const user = userEvent.setup()
    await user.click(screen.getByTestId('action-start'))

    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({
        updateStrategyRequest: { desired_state: 'RUNNING' },
      }),
    )
  })

  it('Stop opens confirmation dialog before calling mutation', async () => {
    renderWithStrategies([
      createMockStrategyResponse({
        name: 'My Strategy',
        actual_state: 'RUNNING',
        enabled: false,
      }),
    ])

    await openActionsDropdown()

    const user = userEvent.setup()
    await user.click(screen.getByTestId('action-stop'))

    // Confirmation dialog should be visible
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent('Stop Strategy')
    expect(dialog).toHaveTextContent('Stop "My Strategy"?')
  })
})

describe('StrategyInstanceColumns — Dropdown activation actions', () => {
  it('shows "Add to active strategies" when enabled is false', async () => {
    renderWithStrategies([createMockStrategyResponse({ enabled: false, actual_state: 'RUNNING' })])

    await openActionsDropdown()

    expect(screen.getByTestId('action-activate')).toHaveTextContent('Add to active strategies')
    expect(screen.queryByTestId('action-deactivate')).not.toBeInTheDocument()
  })

  it('shows "Remove from active" when enabled is true', async () => {
    renderWithStrategies([createMockStrategyResponse({ enabled: true, actual_state: 'RUNNING' })])

    await openActionsDropdown()

    expect(screen.getByTestId('action-deactivate')).toHaveTextContent('Remove from active')
    expect(screen.queryByTestId('action-activate')).not.toBeInTheDocument()
  })

  it('Add to active strategies opens typed confirmation dialog with ACTIVATE word', async () => {
    renderWithStrategies([
      createMockStrategyResponse({
        name: 'Conservative VFMR',
        template_type_id: 'vfmr',
        template_version: '2.0.0',
        enabled: false,
        actual_state: 'RUNNING',
      }),
    ])

    await openActionsDropdown()

    const user = userEvent.setup()
    await user.click(screen.getByTestId('action-activate'))

    // Typed confirmation dialog should be visible
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent('Add to active strategies')
    expect(dialog).toHaveTextContent('Conservative VFMR')
    expect(dialog).toHaveTextContent('vfmr')
    expect(dialog).toHaveTextContent('v2.0.0')

    // Confirm button should be disabled until typing ACTIVATE
    const confirmBtn = within(dialog).getByRole('button', { name: /Add to active/i })
    expect(confirmBtn).toBeDisabled()

    // Type the confirmation word
    const input = screen.getByPlaceholderText('ACTIVATE')
    await user.type(input, 'ACTIVATE')

    expect(confirmBtn).toBeEnabled()
  })

  it('Add to active strategies calls mutation on confirmation', async () => {
    const spy = vi
      .spyOn(controlApi, 'activateStrategyApiV1CommandsLiveStrategiesStrategyIdActivatePost')
      .mockResolvedValue(mockAxiosResponse({ data: mockCommandResponse }))

    // Need to also mock refetch on success
    ;(controlApi.getStrategiesApiV1StateStrategiesGet as Mock).mockResolvedValue(
      mockAxiosResponse({
        data: createMockStrategiesResponse({ strategies: [] }),
      }),
    )

    renderWithStrategies([
      createMockStrategyResponse({
        strategy_id: 'strat-act',
        enabled: false,
        actual_state: 'RUNNING',
      }),
    ])

    await openActionsDropdown()

    const user = userEvent.setup()
    await user.click(screen.getByTestId('action-activate'))

    const input = screen.getByPlaceholderText('ACTIVATE')
    await user.type(input, 'ACTIVATE')

    const dialog = screen.getByRole('alertdialog')
    const confirmBtn = within(dialog).getByRole('button', { name: /Add to active/i })
    await user.click(confirmBtn)

    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({
        strategyId: 'strat-act',
      }),
    )
  })

  it('Remove from active opens standard confirmation dialog', async () => {
    renderWithStrategies([
      createMockStrategyResponse({
        name: 'Aggressive VFMR',
        enabled: true,
        actual_state: 'RUNNING',
      }),
    ])

    await openActionsDropdown()

    const user = userEvent.setup()
    await user.click(screen.getByTestId('action-deactivate'))

    // Standard confirmation dialog should be visible
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent('Remove from active strategies')
    expect(dialog).toHaveTextContent('Aggressive VFMR')
    expect(dialog).toHaveTextContent('paper mode only')
  })

  it('dropdown shows both lifecycle and activation actions together', async () => {
    renderWithStrategies([
      createMockStrategyResponse({
        actual_state: 'STOPPED',
        enabled: true,
      }),
    ])

    await openActionsDropdown()

    // Lifecycle: Start should be visible (STOPPED)
    expect(screen.getByTestId('action-start')).toBeInTheDocument()
    // Activation: Deactivate should be visible (enabled)
    expect(screen.getByTestId('action-deactivate')).toBeInTheDocument()
  })
})
