import type { MarketInfoResponse } from '../lib/api/models/market-info-response'
import type { MarketsResponse } from '../lib/api/models/markets-response'
import type { MarketTickResponse } from '../lib/api/models/market-tick-response'
import type { StrategyTypeResponse } from '../lib/api/models/strategy-type-response'
import type { StrategyTypesResponse } from '../lib/api/models/strategy-types-response'

const defaultMarket: MarketInfoResponse = {
  market_slug: 'btc-updown-15m-1767900600',
  outcome: 'UP',
  latest_tick_ts: '2025-01-27T12:00:00Z',
  active: false,
  start_date: '2025-01-27T12:00:00Z',
  end_date: '2025-01-27T12:15:00Z',
}

export const createMockMarket = (
  overrides: Partial<MarketInfoResponse> = {},
): MarketInfoResponse => ({
  ...defaultMarket,
  ...overrides,
})

export const createMockMarketsResponse = (
  overrides: Partial<MarketsResponse> = {},
): MarketsResponse => ({
  markets: overrides.markets ?? [],
  count: overrides.count ?? 0,
  ...overrides,
})

const defaultMarketTick: MarketTickResponse = {
  tick_id: '00000000-0000-0000-0000-000000000001',
  ts_wall: '2025-01-27T12:00:00Z',
  ts_mono: 0,
  market_slug: 'btc-updown-15m-1767900600',
  outcome: 'UP',
  best_bid: '0.45',
  best_ask: '0.55',
  mid: '0.50',
  spread: '0.10',
  spread_bps: '1000',
}

export const createMockMarketTick = (
  overrides: Partial<MarketTickResponse> = {},
): MarketTickResponse => ({
  ...defaultMarketTick,
  ...overrides,
})

const defaultStrategyType: StrategyTypeResponse = {
  type_id: 'simple_threshold',
  name: 'Simple threshold',
  description: 'Threshold-based strategy',
  available_versions: ['1.0.0', '1.1.0'],
  parameter_schema: {},
}

export const createMockStrategyType = (
  overrides: Partial<StrategyTypeResponse> = {},
): StrategyTypeResponse => ({
  ...defaultStrategyType,
  ...overrides,
})

export const createMockStrategyTypesResponse = (
  overrides: Partial<StrategyTypesResponse> = {},
): StrategyTypesResponse => ({
  types: overrides.types ?? [],
  ...overrides,
})
