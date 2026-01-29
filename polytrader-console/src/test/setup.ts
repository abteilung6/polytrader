/**
 * Central test setup: patch API client so tests never hit the network.
 * All endpoints are stubbed automatically from the actual API class prototypes.
 */
import { vi } from 'vitest'

const defaultResolved = () => Promise.resolve({ data: {} })

const getMethodNames = (obj: object): string[] => {
  const names: string[] = []
  let proto: object | null = Object.getPrototypeOf(obj) as object | null
  while (proto && proto !== Object.prototype) {
    const ownNames: string[] = Object.getOwnPropertyNames(proto)
    for (const name of ownNames) {
      const val: unknown = (obj as Record<string, unknown>)[name]
      if (name !== 'constructor' && typeof val === 'function') {
        names.push(name)
      }
    }
    proto = Object.getPrototypeOf(proto) as object | null
  }
  return [...new Set(names)]
}

const stubApi = (api: object): Record<string, unknown> => {
  const stub: Record<string, unknown> = {}
  for (const key of getMethodNames(api)) {
    stub[key] = vi.fn(defaultResolved)
  }
  return stub
}

vi.mock('../lib/api-client', async (importOriginal) => {
  // importOriginal() is unknown to tsc; assertion required for type-check (ESLint flags as unnecessary)
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-type-assertion
  const actual = (await importOriginal()) as { marketApi: object; controlApi: object }
  return {
    marketApi: stubApi(actual.marketApi),
    controlApi: stubApi(actual.controlApi),
  }
})
