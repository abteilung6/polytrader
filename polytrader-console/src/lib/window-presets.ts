/**
 * Pure helper for computing time window ranges from preset labels.
 *
 * Returns ISO 8601 UTC strings suitable for the performance overview API.
 * Injectable `now` parameter for deterministic testing.
 */

export type WindowPreset = '1d' | '3d' | '7d' | 'all'

export const WINDOW_PRESETS: readonly { value: WindowPreset; label: string }[] = [
  { value: '1d', label: '1d' },
  { value: '3d', label: '3d' },
  { value: '7d', label: '7d' },
  { value: 'all', label: 'All' },
] as const

export const DEFAULT_WINDOW: WindowPreset = '1d'

/** Hours offset for each preset (undefined = no lower bound). */
const HOURS_MAP: Record<WindowPreset, number | undefined> = {
  '1d': 24,
  '3d': 72,
  '7d': 168,
  all: undefined,
}

export interface WindowRange {
  /** ISO 8601 UTC lower bound, or undefined for "all time". */
  since: string | undefined
  /** ISO 8601 UTC upper bound. */
  until: string
}

/**
 * Compute the since/until range for a window preset.
 *
 * @param preset - One of the WindowPreset values.
 * @param now - Current time (injectable for testing). Defaults to new Date().
 * @returns WindowRange with ISO 8601 UTC strings.
 */
export function computeWindowRange(preset: WindowPreset, now: Date = new Date()): WindowRange {
  const until = now.toISOString()
  const hours = HOURS_MAP[preset]

  if (hours === undefined) {
    return { since: undefined, until }
  }

  const sinceDate = new Date(now.getTime() - hours * 60 * 60 * 1000)
  return { since: sinceDate.toISOString(), until }
}
