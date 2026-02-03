const API_BASE = import.meta.env.VITE_API_BASE || ''

// API key — read from env var at build time, or sessionStorage at runtime
let _apiKey: string | null = import.meta.env.VITE_GPS_API_KEY || sessionStorage.getItem('gps_api_key')

export function getApiKey(): string | null { return _apiKey }

export function setApiKey(key: string) {
  _apiKey = key
  sessionStorage.setItem('gps_api_key', key)
}

/** Fetch an audio URL using header auth, returning an object URL for playback. */
export async function fetchAudioUrl(url: string): Promise<string> {
  const resp = await apiFetch(url)
  if (!resp.ok) throw new Error(`Audio fetch failed: ${resp.status}`)
  const blob = await resp.blob()
  return URL.createObjectURL(blob)
}

export const apiUrl = (path: string) => `${API_BASE}${path}`

export const wsUrl = (path: string) => {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return API_BASE
    ? `${proto}//${new URL(API_BASE).host}${path}`
    : `${proto}//${location.host}${path}`
}

/** Fetch wrapper that automatically includes the API key header. */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers)
  if (_apiKey) headers.set('X-API-Key', _apiKey)
  return fetch(apiUrl(path), { ...init, headers })
}
