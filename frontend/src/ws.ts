import { wsUrl, getApiKey } from './api'

export type WSHandler = (data: Record<string, unknown>) => void

export class GPSWebSocket {
  private ws: WebSocket | null = null
  private pingInterval: ReturnType<typeof setInterval> | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private dead = false
  private handlers: Map<string, WSHandler[]> = new Map()
  private onStatusChange: ((connected: boolean) => void) | null = null

  constructor(onStatusChange?: (connected: boolean) => void) {
    this.onStatusChange = onStatusChange || null
  }

  start() {
    this.dead = false
    this.connect()
    document.addEventListener('visibilitychange', this.handleVisibility)
  }

  stop() {
    this.dead = true
    document.removeEventListener('visibilitychange', this.handleVisibility)
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    if (this.pingInterval) clearInterval(this.pingInterval)
    if (this.ws) this.ws.close()
  }

  on(type: string, handler: WSHandler) {
    const list = this.handlers.get(type) || []
    list.push(handler)
    this.handlers.set(type, list)
  }

  off(type: string, handler: WSHandler) {
    const list = this.handlers.get(type) || []
    this.handlers.set(type, list.filter(h => h !== handler))
  }

  send(data: Record<string, unknown>) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    }
  }

  private handleVisibility = () => {
    if (document.visibilityState === 'visible' && (!this.ws || this.ws.readyState !== WebSocket.OPEN)) {
      this.connect()
    }
  }

  private connect() {
    if (this.dead) return
    try {
      this.ws = new WebSocket(wsUrl('/ws'))
    } catch {
      this.retry()
      return
    }

    this.ws.onopen = () => {
      // Send auth message before anything else
      const key = getApiKey()
      if (key && this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'auth', api_key: key }))
      }
      this.onStatusChange?.(true)
      this.pingInterval = setInterval(() => {
        if (this.ws?.readyState === WebSocket.OPEN) this.ws.send('ping')
      }, 30000)
    }

    this.ws.onmessage = (e) => {
      if (e.data === 'pong') return
      try {
        const data = JSON.parse(e.data) as Record<string, unknown>
        const type = data.type as string
        if (!type) return
        const list = this.handlers.get(type)
        if (list) list.forEach(h => h(data))
        // Also fire wildcard handlers
        const wildcardList = this.handlers.get('*')
        if (wildcardList) wildcardList.forEach(h => h(data))
      } catch { /* ignore parse errors */ }
    }

    this.ws.onclose = () => {
      this.onStatusChange?.(false)
      if (this.pingInterval) clearInterval(this.pingInterval)
      this.retry()
    }

    this.ws.onerror = () => { /* onclose will fire */ }
  }

  private retry() {
    if (!this.dead) {
      this.reconnectTimer = setTimeout(() => this.connect(), 3000)
    }
  }
}
