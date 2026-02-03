import { useRef } from 'react'

interface PrinterControlsProps {
  printing: boolean
  onStart: (fileName: string) => void
  onStop: () => void
  onUpload: (file: File) => void
}

export function PrinterControls({ printing, onStop, onUpload }: PrinterControlsProps) {
  const fileRef = useRef<HTMLInputElement>(null)

  const handleUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) onUpload(file)
    if (fileRef.current) fileRef.current.value = ''
  }

  return (
    <div className="printer-card">
      <h3 className="printer-card-title">Controls</h3>
      <div className="printer-controls-row">
        <input
          ref={fileRef}
          type="file"
          accept=".gcode,.gco,.g"
          onChange={handleUpload}
          style={{ display: 'none' }}
        />
        <button
          className="printer-btn printer-btn-primary"
          onClick={() => fileRef.current?.click()}
        >
          Upload G-code
        </button>
        {printing && (
          <button className="printer-btn printer-btn-danger" onClick={onStop}>
            Stop Print
          </button>
        )}
      </div>
    </div>
  )
}
