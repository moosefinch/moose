import { useState } from 'react'
import { ThreeViewport } from '../components/viewport/ThreeViewport'
import { ViewportToolbar } from '../components/viewport/ViewportToolbar'

export function ViewportPage() {
  const [modelUrl, setModelUrl] = useState<string | null>(null)
  const [modelType, setModelType] = useState<string>('stl')
  const [wireframe, setWireframe] = useState(false)
  const [showGrid, setShowGrid] = useState(true)
  const [resetKey, setResetKey] = useState(0)

  const handleFileLoad = (url: string, type: string) => {
    setModelUrl(url)
    setModelType(type)
  }

  return (
    <div className="page-viewport">
      <ViewportToolbar
        wireframe={wireframe}
        showGrid={showGrid}
        onToggleWireframe={() => setWireframe(w => !w)}
        onToggleGrid={() => setShowGrid(g => !g)}
        onResetView={() => setResetKey(k => k + 1)}
        onFileLoad={handleFileLoad}
      />
      <ThreeViewport
        modelUrl={modelUrl}
        modelType={modelType}
        wireframe={wireframe}
        showGrid={showGrid}
        resetKey={resetKey}
      />
    </div>
  )
}
