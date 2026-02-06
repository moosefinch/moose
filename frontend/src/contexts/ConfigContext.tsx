import { createContext, useContext, useState, useEffect } from 'react'
import type { ReactNode } from 'react'
import { apiUrl } from '../api'

interface Config {
  systemName: string
  version: string
  enabledPlugins: string[]
  advocacyEnabled: boolean
  cognitiveLoopEnabled: boolean
}

const defaultConfig: Config = {
  systemName: 'Moose',
  version: '',
  enabledPlugins: [],
  advocacyEnabled: false,
  cognitiveLoopEnabled: false,
}

const ConfigContext = createContext<Config>(defaultConfig)

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<Config>(defaultConfig)

  useEffect(() => {
    let cancelled = false
    fetch(apiUrl('/api/config'))
      .then(r => r.json())
      .then((data: { system_name: string; version: string; enabled_plugins: string[]; advocacy_enabled?: boolean; cognitive_loop_enabled?: boolean }) => {
        if (cancelled) return
        setConfig({
          systemName: data.system_name || defaultConfig.systemName,
          version: data.version || '',
          enabledPlugins: data.enabled_plugins || [],
          advocacyEnabled: data.advocacy_enabled || false,
          cognitiveLoopEnabled: data.cognitive_loop_enabled || false,
        })
      })
      .catch(err => {
        console.warn('[ConfigContext] Failed to fetch config:', err)
      })
    return () => { cancelled = true }
  }, [])

  return (
    <ConfigContext.Provider value={config}>
      {children}
    </ConfigContext.Provider>
  )
}

export function useConfig(): Config {
  return useContext(ConfigContext)
}
