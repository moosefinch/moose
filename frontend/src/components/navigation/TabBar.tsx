import { useNavigation, type Page } from '../../contexts/NavigationContext'

const TABS: { id: Page; label: string; shortcut: string }[] = [
  { id: 'more', label: 'Home', shortcut: '1' },
  { id: 'dashboard', label: 'Dashboard', shortcut: '2' },
  { id: 'viewport', label: 'Viewport', shortcut: '3' },
]

export function TabBar() {
  const { page, setPage } = useNavigation()

  return (
    <nav className="tab-bar">
      <div className="tab-bar-logo">
        <span className="tab-bar-brand">Moose</span>
      </div>

      <div className="tab-bar-tabs">
        {TABS.map(tab => (
          <button
            key={tab.id}
            className={`tab-bar-tab ${page === tab.id ? 'active' : ''}`}
            onClick={() => setPage(tab.id)}
            title={`${tab.label} (Cmd+${tab.shortcut})`}
          >
            {tab.label}
            <span className="tab-shortcut">{tab.shortcut}</span>
          </button>
        ))}
      </div>
    </nav>
  )
}
