import { createContext, useContext, useState, useCallback, ReactNode } from 'react'

export type Page = 'dashboard' | 'viewport' | 'printer' | 'more'
export type MoreSubPage = 'chat' | 'channels' | 'memory' | 'marketing' | 'scheduling' | 'plugins'

interface NavigationState {
  page: Page
  subPage: MoreSubPage
  setPage: (page: Page) => void
  setSubPage: (sub: MoreSubPage) => void
  navigateTo: (page: Page, sub?: MoreSubPage) => void
}

const NavigationContext = createContext<NavigationState | null>(null)

export function NavigationProvider({ children }: { children: ReactNode }) {
  const [page, setPageState] = useState<Page>('dashboard')
  const [subPage, setSubPage] = useState<MoreSubPage>('chat')

  const setPage = useCallback((p: Page) => setPageState(p), [])

  const navigateTo = useCallback((p: Page, sub?: MoreSubPage) => {
    setPageState(p)
    if (sub) setSubPage(sub)
  }, [])

  return (
    <NavigationContext.Provider value={{ page, subPage, setPage, setSubPage, navigateTo }}>
      {children}
    </NavigationContext.Provider>
  )
}

export function useNavigation() {
  const ctx = useContext(NavigationContext)
  if (!ctx) throw new Error('useNavigation must be inside NavigationProvider')
  return ctx
}
