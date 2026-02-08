import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

import { controlApi } from '@/lib/api-client'
import type { ExecutionStateResponse } from '@/lib/api'
import { mockAxiosResponse, renderWithQuery } from '@/test/utils'

import { ExecutionControlPanel } from './execution-control-panel'

const baseState: ExecutionStateResponse = {
  execution_enabled: false,
  kill_switch_active: false,
  version: 1,
  updated_at: '2026-02-08T12:00:00Z',
  updated_by: 'system',
  reason: 'Initial state',
}

function mockExecutionState(overrides: Partial<ExecutionStateResponse> = {}) {
  vi.spyOn(controlApi, 'getExecutionStateApiV1StateExecutionGet').mockResolvedValue(
    mockAxiosResponse({ data: { ...baseState, ...overrides } }),
  )
}

describe('ExecutionControlPanel', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders three control rows', async () => {
    mockExecutionState()

    renderWithQuery(<ExecutionControlPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('execution-switch-row')).toBeInTheDocument()
    })
    expect(screen.getByTestId('kill-switch-row')).toBeInTheDocument()
    expect(screen.getByTestId('circuit-breaker-row')).toBeInTheDocument()
  })

  it('shows OFF badge when execution disabled', async () => {
    mockExecutionState({ execution_enabled: false })

    renderWithQuery(<ExecutionControlPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('execution-switch-row')).toHaveTextContent('OFF')
    })
  })

  it('shows ON badge when execution enabled', async () => {
    mockExecutionState({ execution_enabled: true })

    renderWithQuery(<ExecutionControlPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('execution-switch-row')).toHaveTextContent('ON')
    })
  })

  it('shows READY badge when kill switch is not active', async () => {
    mockExecutionState({ kill_switch_active: false })

    renderWithQuery(<ExecutionControlPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('kill-switch-row')).toHaveTextContent('READY')
    })
  })

  it('shows ACTIVE badge when kill switch is active', async () => {
    mockExecutionState({ kill_switch_active: true })

    renderWithQuery(<ExecutionControlPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('kill-switch-row')).toHaveTextContent('ACTIVE')
    })
  })

  it('shows version and timestamp info', async () => {
    mockExecutionState({
      version: 3,
      updated_at: '2026-02-08T14:30:00Z',
      updated_by: 'operator',
    })

    renderWithQuery(<ExecutionControlPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('execution-switch-row')).toHaveTextContent('v3')
      expect(screen.getByTestId('execution-switch-row')).toHaveTextContent('operator')
    })
  })

  it('opens typed enable dialog when switching execution ON', async () => {
    const user = userEvent.setup()
    mockExecutionState({ execution_enabled: false })

    renderWithQuery(<ExecutionControlPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('execution-switch')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('execution-switch'))

    await waitFor(() => {
      const dialog = screen.getByRole('alertdialog')
      expect(dialog).toHaveTextContent('Enable Execution')
      expect(dialog).toHaveTextContent('ENABLE LIVE')
    })
  })

  it('opens standard disable dialog when switching execution OFF', async () => {
    const user = userEvent.setup()
    mockExecutionState({ execution_enabled: true })

    renderWithQuery(<ExecutionControlPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('execution-switch')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('execution-switch'))

    await waitFor(() => {
      const dialog = screen.getByRole('alertdialog')
      expect(dialog).toHaveTextContent('Disable Execution')
    })
  })

  it('opens typed kill dialog when switching kill switch ON', async () => {
    const user = userEvent.setup()
    mockExecutionState({ kill_switch_active: false })

    renderWithQuery(<ExecutionControlPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('kill-switch-toggle')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('kill-switch-toggle'))

    await waitFor(() => {
      const dialog = screen.getByRole('alertdialog')
      expect(dialog).toHaveTextContent('Activate Kill Switch')
    })

    // Should have typed confirmation input
    expect(screen.getByPlaceholderText('KILL')).toBeInTheDocument()
  })

  it('opens reset dialog when switching kill switch OFF', async () => {
    const user = userEvent.setup()
    mockExecutionState({ kill_switch_active: true })

    renderWithQuery(<ExecutionControlPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('kill-switch-toggle')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('kill-switch-toggle'))

    await waitFor(() => {
      const dialog = screen.getByRole('alertdialog')
      expect(dialog).toHaveTextContent('Reset Kill Switch')
    })
  })

  it('circuit breaker switch is disabled (read-only)', async () => {
    mockExecutionState()

    renderWithQuery(<ExecutionControlPanel />)

    await waitFor(() => {
      expect(screen.getByLabelText('Circuit breaker status')).toBeDisabled()
    })
  })
})
