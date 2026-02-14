import { screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'

import { controlApi } from '@/lib/api-client'
import type { ExecutionStateResponse } from '@/lib/api'
import { mockAxiosResponse, renderWithQuery } from '@/test/utils'

import { EnvironmentBadge } from './environment-badge'

const baseState: ExecutionStateResponse = {
  execution_enabled: false,
  kill_switch_active: false,
  version: 1,
  updated_at: '2026-02-08T12:00:00Z',
  updated_by: 'system',
  reason: 'Initial state',
}

describe('EnvironmentBadge', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows "PAPER" badge when execution is disabled', async () => {
    vi.spyOn(controlApi, 'getExecutionStateApiV1StateExecutionGet').mockResolvedValue(
      mockAxiosResponse({ data: { ...baseState, execution_enabled: false } }),
    )

    renderWithQuery(<EnvironmentBadge />)

    const badge = await screen.findByTestId('environment-badge')
    expect(badge).toHaveTextContent('PAPER')
  })

  it('shows "LIVE" badge when execution is enabled', async () => {
    vi.spyOn(controlApi, 'getExecutionStateApiV1StateExecutionGet').mockResolvedValue(
      mockAxiosResponse({ data: { ...baseState, execution_enabled: true } }),
    )

    renderWithQuery(<EnvironmentBadge />)

    const badge = await screen.findByTestId('environment-badge')
    expect(badge).toHaveTextContent('LIVE')
  })

  it('shows skeleton while loading', () => {
    // Never-resolving promise simulates loading
    vi.spyOn(controlApi, 'getExecutionStateApiV1StateExecutionGet').mockReturnValue(
      new Promise(() => {}),
    )

    renderWithQuery(<EnvironmentBadge />)

    expect(screen.getByTestId('env-badge-skeleton')).toBeInTheDocument()
  })

  it('has correct aria-label for paper mode', async () => {
    vi.spyOn(controlApi, 'getExecutionStateApiV1StateExecutionGet').mockResolvedValue(
      mockAxiosResponse({ data: { ...baseState, execution_enabled: false } }),
    )

    renderWithQuery(<EnvironmentBadge />)

    await waitFor(() => {
      expect(screen.getByLabelText('Paper trading mode')).toBeInTheDocument()
    })
  })

  it('has correct aria-label for live mode', async () => {
    vi.spyOn(controlApi, 'getExecutionStateApiV1StateExecutionGet').mockResolvedValue(
      mockAxiosResponse({ data: { ...baseState, execution_enabled: true } }),
    )

    renderWithQuery(<EnvironmentBadge />)

    await waitFor(() => {
      expect(screen.getByLabelText('Live execution mode')).toBeInTheDocument()
    })
  })
})
