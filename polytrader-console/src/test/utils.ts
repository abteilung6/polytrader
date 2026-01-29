import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'

export interface MockResponseOptions<T> {
  data: T
  status?: number
  statusText?: string
  headers?: Record<string, string>
}

export const mockAxiosResponse = <T>({
  data,
  status = 200,
  statusText = 'OK',
  headers = {},
}: MockResponseOptions<T>): AxiosResponse<T> => ({
  data,
  status,
  statusText,
  headers,
  config: {} as InternalAxiosRequestConfig,
})
