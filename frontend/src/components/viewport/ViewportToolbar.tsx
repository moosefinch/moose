import { useRef } from 'react'

interface ViewportToolbarProps {
  wireframe: boolean
  showGrid: boolean
  onToggleWireframe: () => void
  onToggleGrid: () => void
  onResetView: () => void
  onFileLoad: (url: string, type: string) => void
}

export function ViewportToolbar({ wireframe, showGrid, onToggleWireframe, onToggleGrid, onResetView, onFileLoad }: ViewportToolbarProps) {
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const ext = file.name.split('.').pop()?.toLowerCase() || ''
    const url = URL.createObjectURL(file)
    onFileLoad(url, ext)
    if (fileRef.current) fileRef.current.value = ''
  }

  return (
    <div className="viewport-toolbar">
      <input
        ref={fileRef}
        type="file"
        accept=".stl,.obj,.gltf,.glb"
        onChange={handleFile}
        style={{ display: 'none' }}
      />
      <button className="vp-tool-btn" onClick={() => fileRef.current?.click()}>
        Open File
      </button>
      <div className="vp-tool-separator" />
      <button
        className={`vp-tool-btn ${wireframe ? 'active' : ''}`}
        onClick={onToggleWireframe}
      >
        Wireframe
      </button>
      <button
        className={`vp-tool-btn ${showGrid ? 'active' : ''}`}
        onClick={onToggleGrid}
      >
        Grid
      </button>
      <button className="vp-tool-btn" onClick={onResetView}>
        Reset View
      </button>
    </div>
  )
}
