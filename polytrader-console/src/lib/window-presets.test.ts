import { describe, it, expect } from 'vitest'

import { computeWindowRange, DEFAULT_WINDOW, WINDOW_PRESETS } from './window-presets'

// Fixed reference time for deterministic tests
const NOW = new Date('2026-02-01T12:00:00.000Z')

describe('computeWindowRange', () => {
  it('returns undefined since for "all" preset', () => {
    const range = computeWindowRange('all', NOW)
    expect(range.since).toBeUndefined()
    expect(range.until).toBe('2026-02-01T12:00:00.000Z')
  })

  it('computes 1d window (24 hours back)', () => {
    const range = computeWindowRange('1d', NOW)
    expect(range.since).toBe('2026-01-31T12:00:00.000Z')
    expect(range.until).toBe('2026-02-01T12:00:00.000Z')
  })

  it('computes 3d window (72 hours back)', () => {
    const range = computeWindowRange('3d', NOW)
    expect(range.since).toBe('2026-01-29T12:00:00.000Z')
    expect(range.until).toBe('2026-02-01T12:00:00.000Z')
  })

  it('computes 7d window (168 hours back)', () => {
    const range = computeWindowRange('7d', NOW)
    expect(range.since).toBe('2026-01-25T12:00:00.000Z')
    expect(range.until).toBe('2026-02-01T12:00:00.000Z')
  })

  it('uses current time when now is not provided', () => {
    const before = new Date().toISOString()
    const range = computeWindowRange('all')
    const after = new Date().toISOString()

    expect(range.since).toBeUndefined()
    expect(range.until >= before).toBe(true)
    expect(range.until <= after).toBe(true)
  })
})

describe('WINDOW_PRESETS', () => {
  it('contains 4 presets', () => {
    expect(WINDOW_PRESETS).toHaveLength(4)
  })

  it('has expected values', () => {
    const values = WINDOW_PRESETS.map((p) => p.value)
    expect(values).toEqual(['1d', '3d', '7d', 'all'])
  })

  it('has human-readable labels', () => {
    const labels = WINDOW_PRESETS.map((p) => p.label)
    expect(labels).toEqual(['1d', '3d', '7d', 'All'])
  })
})

describe('DEFAULT_WINDOW', () => {
  it('is "1d"', () => {
    expect(DEFAULT_WINDOW).toBe('1d')
  })
})
