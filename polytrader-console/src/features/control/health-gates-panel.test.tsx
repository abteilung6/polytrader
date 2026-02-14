import { screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'

import { controlApi } from '@/lib/api-client'
import type { HealthResponse } from '@/lib/api'
import { mockAxiosResponse, renderWithQuery } from '@/test/utils'

import { HealthGatesPanel } from './health-gates-panel'

const healthyResponse: HealthResponse = {
  overall: 'ok',
  gates: {
    db: { status: 'ok', message: 'Connected' },
    market_data_freshness: { status: 'ok', message: '< 5s' },
    event_bus_lag: { status: 'ok', message: '0ms lag' },
    venue_connectivity: { status: 'ok', message: 'Polymarket API reachable' },
    risk_engine: { status: 'ok', message: 'All policies loaded' },
    clock_skew_ms: 42,
  },
}

const degradedResponse: HealthResponse = {
  overall: 'degraded',
  gates: {
    db: { status: 'ok', message: 'Connected' },
    market_data_freshness: { status: 'degraded', message: 'Stale > 30s' },
    event_bus_lag: { status: 'ok', message: '0ms lag' },
    venue_connectivity: { status: 'ok', message: 'Reachable' },
    risk_engine: { status: 'ok', message: 'Loaded' },
    clock_skew_ms: 200,
  },
}

const downResponse: HealthResponse = {
  overall: 'down',
  gates: {
    db: { status: 'down', message: 'Connection refused' },
    market_data_freshness: { status: 'down', message: 'No data' },
    event_bus_lag: { status: 'ok', message: '0ms lag' },
    venue_connectivity: { status: 'down', message: 'Timeout' },
    risk_engine: { status: 'ok', message: 'Loaded' },
    clock_skew_ms: 5000,
  },
}

function mockHealth(response: HealthResponse) {
  vi.spyOn(controlApi, 'getHealthApiV1StateHealthGet').mockResolvedValue(
    mockAxiosResponse({ data: response }),
  )
}

describe('HealthGatesPanel', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders panel with card structure', async () => {
    mockHealth(healthyResponse)

    renderWithQuery(<HealthGatesPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('health-gates-panel')).toBeInTheDocument()
    })
    expect(screen.getByText('Health Gates')).toBeInTheDocument()
  })

  it('shows overall OK badge when all gates healthy', async () => {
    mockHealth(healthyResponse)

    renderWithQuery(<HealthGatesPanel />)

    await waitFor(() => {
      const badge = screen.getByTestId('health-overall-badge')
      expect(badge).toHaveTextContent('OK')
    })
  })

  it('shows overall DEGRADED badge when gates degraded', async () => {
    mockHealth(degradedResponse)

    renderWithQuery(<HealthGatesPanel />)

    await waitFor(() => {
      const badge = screen.getByTestId('health-overall-badge')
      expect(badge).toHaveTextContent('DEGRADED')
    })
  })

  it('shows overall DOWN badge when gates down', async () => {
    mockHealth(downResponse)

    renderWithQuery(<HealthGatesPanel />)

    await waitFor(() => {
      const badge = screen.getByTestId('health-overall-badge')
      expect(badge).toHaveTextContent('DOWN')
    })
  })

  it('displays all gate rows', async () => {
    mockHealth(healthyResponse)

    renderWithQuery(<HealthGatesPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('health-gate-db')).toBeInTheDocument()
    })
    expect(screen.getByTestId('health-gate-market_data_freshness')).toBeInTheDocument()
    expect(screen.getByTestId('health-gate-event_bus_lag')).toBeInTheDocument()
    expect(screen.getByTestId('health-gate-venue_connectivity')).toBeInTheDocument()
    expect(screen.getByTestId('health-gate-risk_engine')).toBeInTheDocument()
    expect(screen.getByTestId('health-gate-clock_skew')).toBeInTheDocument()
  })

  it('shows human-readable gate labels', async () => {
    mockHealth(healthyResponse)

    renderWithQuery(<HealthGatesPanel />)

    await waitFor(() => {
      expect(screen.getByText('Database')).toBeInTheDocument()
    })
    expect(screen.getByText('Market Data')).toBeInTheDocument()
    expect(screen.getByText('Event Bus')).toBeInTheDocument()
    expect(screen.getByText('Venue API')).toBeInTheDocument()
    expect(screen.getByText('Risk Engine')).toBeInTheDocument()
    expect(screen.getByText('Clock Skew')).toBeInTheDocument()
  })

  it('shows gate detail messages', async () => {
    mockHealth(healthyResponse)

    renderWithQuery(<HealthGatesPanel />)

    await waitFor(() => {
      expect(screen.getByText('Connected')).toBeInTheDocument()
    })
    expect(screen.getByText('< 5s')).toBeInTheDocument()
    expect(screen.getByText('Polymarket API reachable')).toBeInTheDocument()
  })

  it('shows clock skew value', async () => {
    mockHealth(healthyResponse)

    renderWithQuery(<HealthGatesPanel />)

    await waitFor(() => {
      expect(screen.getByText('42ms')).toBeInTheDocument()
    })
  })

  it('shows loading skeletons while fetching', () => {
    vi.spyOn(controlApi, 'getHealthApiV1StateHealthGet').mockReturnValue(new Promise(() => {}))

    renderWithQuery(<HealthGatesPanel />)

    expect(screen.getByTestId('health-loading')).toBeInTheDocument()
  })

  it('shows error message on failure', async () => {
    vi.spyOn(controlApi, 'getHealthApiV1StateHealthGet').mockRejectedValue(
      new Error('Network error'),
    )

    renderWithQuery(<HealthGatesPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('health-error')).toBeInTheDocument()
    })
    expect(screen.getByTestId('health-error')).toHaveTextContent('Network error')
  })
})
