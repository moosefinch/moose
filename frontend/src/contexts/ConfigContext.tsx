import { createContext, useContext, useState, useEffect } from 'react'
import type { ReactNode } from 'react'
import { apiUrl } from '../api'

interface Config {
  systemName: string
  version: string
  enabledPlugins: string[]
}

const defaultConfig: Config = {
  systemName: 'Moose',
  version: '',
  enabledPlugins: [],
}

const ConfigContext = createContext<Config>(defaultConfig)

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<Config>(defaultConfig)

  useEffect(() => {
    let cancelled = false
    fetch(apiUrl('/api/config'))
      .then(r => r.json())
      .then((data: { system_name: string; version: string; enabled_plugins: string[] }) => {
        if (cancelled) return
        setConfig({
          systemName: data.system_name || defaultConfig.systemName,
          version: data.version || '',
          enabledPlugins: data.enabled_plugins || [],
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
