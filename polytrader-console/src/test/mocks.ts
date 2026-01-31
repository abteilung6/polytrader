import type { ClosedTradeItem } from '../lib/api/models/closed-trade-item'
import type { MarketInfoResponse } from '../lib/api/models/market-info-response'
import type { MarketsResponse } from '../lib/api/models/markets-response'
import type { MarketTickResponse } from '../lib/api/models/market-tick-response'
import type { PerformanceResponse } from '../lib/api/models/performance-response'
import type { PerformanceSummary } from '../lib/api/models/performance-summary'
import type { StrategyOrderItem } from '../lib/api/models/strategy-order-item'
import type { StrategyOrdersResponse } from '../lib/api/models/strategy-orders-response'
import type { StrategyResponse } from '../lib/api/models/strategy-response'
import type { StrategiesResponse } from '../lib/api/models/strategies-response'
import type { StrategySignalItem } from '../lib/api/models/strategy-signal-item'
import type { StrategySignalsResponse } from '../lib/api/models/strategy-signals-response'
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

const defaultStrategy: StrategyResponse = {
  strategy_id: 'strat-001',
  name: 'My threshold strategy',
  config: {},
  template_type_id: 'simple_threshold',
  template_version: '1.1.0',
  desired_state: 'RUNNING',
  actual_state: 'RUNNING',
  created_at: '2025-01-27T12:00:00Z',
  updated_at: '2025-01-27T12:00:00Z',
  enabled: true,
}

export const createMockStrategyResponse = (
  overrides: Partial<StrategyResponse> = {},
): StrategyResponse => ({
  ...defaultStrategy,
  ...overrides,
})

export const createMockStrategiesResponse = (
  overrides: Partial<StrategiesResponse> = {},
): StrategiesResponse => ({
  strategies: overrides.strategies ?? [],
  ...overrides,
})

const defaultStrategySignal: StrategySignalItem = {
  event_id: '00000000-0000-0000-0000-000000000001',
  ts_wall: '2025-01-27T12:00:00Z',
  market_slug: 'btc-updown-15m',
  outcome: 'UP',
  p_up: 0.6,
  p_down: 0.4,
  edge: 0.1,
  confidence: 0.8,
  model_id: 'strat-001',
  model_version: '1.0.0',
  rationale: 'Test signal',
}

export const createMockStrategySignalItem = (
  overrides: Partial<StrategySignalItem> = {},
): StrategySignalItem => ({
  ...defaultStrategySignal,
  ...overrides,
})

export const createMockStrategySignalsResponse = (
  overrides: Partial<StrategySignalsResponse> = {},
): StrategySignalsResponse => ({
  items: overrides.items ?? [],
  next_cursor: overrides.next_cursor ?? null,
  ...overrides,
})

const defaultStrategyOrder: StrategyOrderItem = {
  order_id: '00000000-0000-0000-0000-000000000002',
  client_order_id: 'client-001',
  ts_wall: '2025-01-27T12:00:00Z',
  market_slug: 'btc-updown-15m',
  side: 'BUY',
  size: 100,
  limit_price: 0.45,
  status: 'PENDING_SUBMIT',
  execution_mode: 'paper',
}

export const createMockStrategyOrderItem = (
  overrides: Partial<StrategyOrderItem> = {},
): StrategyOrderItem => ({
  ...defaultStrategyOrder,
  ...overrides,
})

export const createMockStrategyOrdersResponse = (
  overrides: Partial<StrategyOrdersResponse> = {},
): StrategyOrdersResponse => ({
  items: overrides.items ?? [],
  next_cursor: overrides.next_cursor ?? null,
  ...overrides,
})

const defaultClosedTradeItem: ClosedTradeItem = {
  market_slug: 'btc-updown-15m',
  outcome: 'UP',
  entry_time: 1000,
  exit_time: 1100,
  exit_ts_wall: '2025-01-27T12:00:00Z',
  entry_price: 0.45,
  exit_price: 0.55,
  size: 100,
  pnl: 10,
  pnl_pct: 22.2,
  result: 'WIN',
  execution_mode: 'paper',
  duration_seconds: 100,
}

export const createMockClosedTradeItem = (
  overrides: Partial<ClosedTradeItem> = {},
): ClosedTradeItem => ({
  ...defaultClosedTradeItem,
  ...overrides,
})

const defaultPerformanceSummary: PerformanceSummary = {
  total_realized_pnl: 10,
  total_trades: 1,
  win_rate_pct: 100,
  current_drawdown: null,
  max_drawdown: null,
}

export const createMockPerformanceSummary = (
  overrides: Partial<PerformanceSummary> = {},
): PerformanceSummary => ({
  ...defaultPerformanceSummary,
  ...overrides,
})

export const createMockPerformanceResponse = (
  overrides: Partial<PerformanceResponse> = {},
): PerformanceResponse => ({
  summary: overrides.summary ?? defaultPerformanceSummary,
  items: overrides.items ?? [],
  next_cursor: overrides.next_cursor ?? null,
  ...overrides,
})
