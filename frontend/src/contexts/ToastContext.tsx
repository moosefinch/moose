import { createContext, useContext, useState, useCallback, ReactNode } from 'react'

interface ToastItem {
  id: string
  content: string
  type?: 'default' | 'ai' | 'success' | 'error'
  duration?: number
}

interface ToastState {
  toasts: ToastItem[]
  addToast: (content: string, opts?: { type?: ToastItem['type']; duration?: number }) => void
  dismissToast: (id: string) => void
}

const ToastContext = createContext<ToastState | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const addToast = useCallback((content: string, opts?: { type?: ToastItem['type']; duration?: number }) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
    const duration = opts?.duration ?? 6000
    const toast: ToastItem = { id, content, type: opts?.type ?? 'default', duration }
    setToasts(prev => [...prev, toast])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), duration)
  }, [])

  const dismissToast = useCallback((id: string) => {
    setToasts(t => t.filter(x => x.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ toasts, addToast, dismissToast }}>
      {children}
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be inside ToastProvider')
  return ctx
}
