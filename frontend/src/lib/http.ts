import axios from 'axios'

export const AUTH_TOKEN_STORAGE_KEY = 'framedrama_access_token'

export function readStoredToken(): string | null {
  try {
    return typeof localStorage !== 'undefined' ? localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) : null
  } catch {
    return null
  }
}

export function writeStoredToken(token: string | null): void {
  try {
    if (typeof localStorage === 'undefined') return
    if (token) localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token)
    else localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY)
  } catch {
    // Ignore storage quota or privacy-mode errors.
  }
}

export interface ApiEnvelope<T> {
  code: string
  message: string
  data: T
}

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30_000,
  headers: { Accept: 'application/json' },
})

http.interceptors.request.use((config) => {
  const token = readStoredToken()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export function unwrap<T>(request: Promise<{ data: ApiEnvelope<T> }>): Promise<T> {
  return request.then((response) => response.data.data)
}
