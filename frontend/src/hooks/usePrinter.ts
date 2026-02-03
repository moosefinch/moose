import { useState, useEffect, useCallback } from 'react'
import { apiFetch, apiUrl, getApiKey } from '../api'
import { useWebSocket } from './useWebSocket'

export interface PrinterStatus {
  state?: string
  nozzle_temp?: number
  nozzle_target?: number
  bed_temp?: number
  bed_target?: number
  progress?: number
  current_file?: string
  current_layer?: number
  total_layers?: number
  eta?: string
  connected?: boolean
}

export interface PrinterFile {
  name: string
  size?: number
  date?: string
}

export function usePrinter() {
  const [status, setStatus] = useState<PrinterStatus | null>(null)
  const [files, setFiles] = useState<PrinterFile[]>([])
  const [loading, setLoading] = useState(false)
  const { on, off } = useWebSocket()

  // Poll status every 5s
  useEffect(() => {
    const poll = async () => {
      try {
        const r = await apiFetch('/api/printer/status')
        if (r.ok) setStatus(await r.json())
      } catch { /* printer offline */ }
    }
    poll()
    const id = setInterval(poll, 5000)
    return () => clearInterval(id)
  }, [])

  // Listen for WebSocket printer updates
  useEffect(() => {
    const handleStatus = (data: Record<string, unknown>) => {
      setStatus(data as unknown as PrinterStatus)
    }
    on('printer_status', handleStatus)
    return () => off('printer_status', handleStatus)
  }, [on, off])

  // Load file list
  const loadFiles = useCallback(async () => {
    setLoading(true)
    try {
      const r = await apiFetch('/api/printer/files')
      if (r.ok) {
        const data = await r.json()
        setFiles(Array.isArray(data) ? data : data.files || [])
      }
    } catch { /* offline */ }
    setLoading(false)
  }, [])

  useEffect(() => { loadFiles() }, [loadFiles])

  const startPrint = useCallback(async (fileName: string) => {
    try {
      await apiFetch('/api/printer/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_name: fileName }),
      })
    } catch (e) { console.error('[usePrinter] start failed:', e) }
  }, [])

  const stopPrint = useCallback(async () => {
    try {
      await apiFetch('/api/printer/stop', { method: 'POST' })
    } catch (e) { console.error('[usePrinter] stop failed:', e) }
  }, [])

  const uploadFile = useCallback(async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    try {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', apiUrl('/api/printer/upload'))
      const key = getApiKey()
      if (key) xhr.setRequestHeader('X-API-Key', key)
      xhr.onload = () => loadFiles()
      xhr.send(formData)
    } catch (e) { console.error('[usePrinter] upload failed:', e) }
  }, [loadFiles])

  return { status, files, loading, startPrint, stopPrint, uploadFile, loadFiles }
}
