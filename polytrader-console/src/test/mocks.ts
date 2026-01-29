import type { MarketInfoResponse } from '../lib/api/models/market-info-response'
import type { MarketsResponse } from '../lib/api/models/markets-response'
import type { MarketTickResponse } from '../lib/api/models/market-tick-response'

const defaultMarket: MarketInfoResponse = {
  market_slug: 'btc-updown-15m-1767900600',
  outcome: 'UP',
  latest_tick_ts: '2025-01-27T12:00:00Z',
  active: false,
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
