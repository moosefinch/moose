import type { PrinterFile } from '../../hooks/usePrinter'

interface PrinterFileListProps {
  files: PrinterFile[]
  onStartFile: (fileName: string) => void
  loading: boolean
}

export function PrinterFileList({ files, onStartFile, loading }: PrinterFileListProps) {
  return (
    <div className="printer-card">
      <h3 className="printer-card-title">Files on Printer</h3>
      {loading ? (
        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Loading...</p>
      ) : files.length === 0 ? (
        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No files found</p>
      ) : (
        <div className="printer-file-list">
          {files.map(f => (
            <div key={f.name} className="printer-file-item">
              <span className="printer-file-name">{f.name}</span>
              {f.size != null && (
                <span className="printer-file-size">
                  {(f.size / 1024).toFixed(0)} KB
                </span>
              )}
              <button
                className="printer-file-start"
                onClick={() => onStartFile(f.name)}
                title="Start print"
              >
                &#9654;
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
