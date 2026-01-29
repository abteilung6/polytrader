import { Configuration, ControlApi, MarketApi } from './api'

const API_URL: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

const config = new Configuration({
  basePath: API_URL,
})

export const controlApi = new ControlApi(config)
export const marketApi = new MarketApi(config)
