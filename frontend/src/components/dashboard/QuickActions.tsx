import { useState } from 'react'

interface QuickActionsProps {
  onLaunchTask: (description: string) => void
  onNavigateViewport: () => void
}

export function QuickActions({ onLaunchTask, onNavigateViewport }: QuickActionsProps) {
  const [taskInput, setTaskInput] = useState('')

  const handleLaunch = () => {
    if (taskInput.trim()) {
      onLaunchTask(taskInput.trim())
      setTaskInput('')
    }
  }

  return (
    <div className="dashboard-card">
      <h3 className="dashboard-card-title">Quick Actions</h3>
      <div className="quick-actions-grid">
        <button className="quick-action-btn" onClick={onNavigateViewport}>
          <span className="quick-action-icon">&#9653;</span>
          Open Viewport
        </button>
        <button className="quick-action-btn" onClick={() => {
          const input = document.createElement('input')
          input.type = 'file'
          input.accept = '.stl,.obj,.gltf,.glb,.blend'
          input.click()
        }}>
          <span className="quick-action-icon">&#8689;</span>
          Import Model
        </button>
      </div>
      <div className="quick-task-input">
        <input
          type="text"
          placeholder="Launch a task..."
          value={taskInput}
          onChange={e => setTaskInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleLaunch()}
        />
        <button onClick={handleLaunch} disabled={!taskInput.trim()}>Go</button>
      </div>
    </div>
  )
}
