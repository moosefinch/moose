import { useEffect, useRef, useState, useCallback } from 'react'
import { GPSWebSocket, WSHandler } from '../ws'

export function useWebSocket() {
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<GPSWebSocket | null>(null)

  useEffect(() => {
    const ws = new GPSWebSocket(setConnected)
    wsRef.current = ws
    ws.start()
    return () => ws.stop()
  }, [])

  const on = useCallback((type: string, handler: WSHandler) => {
    wsRef.current?.on(type, handler)
  }, [])

  const off = useCallback((type: string, handler: WSHandler) => {
    wsRef.current?.off(type, handler)
  }, [])

  const send = useCallback((data: Record<string, unknown>) => {
    wsRef.current?.send(data)
  }, [])

  return { connected, on, off, send }
}
