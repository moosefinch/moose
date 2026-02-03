import { PrinterDashboard } from '../components/printer/PrinterDashboard'
import { TemperatureGauge } from '../components/printer/TemperatureGauge'
import { PrintProgress } from '../components/printer/PrintProgress'
import { PrinterControls } from '../components/printer/PrinterControls'
import { PrinterFileList } from '../components/printer/PrinterFileList'
import { usePrinter } from '../hooks/usePrinter'

export function PrinterPage() {
  const printer = usePrinter()

  return (
    <div className="page-printer">
      <div className="printer-grid">
        <div className="printer-col-left">
          <PrinterDashboard status={printer.status} />
          <TemperatureGauge
            nozzleTemp={printer.status?.nozzle_temp ?? 0}
            nozzleTarget={printer.status?.nozzle_target ?? 0}
            bedTemp={printer.status?.bed_temp ?? 0}
            bedTarget={printer.status?.bed_target ?? 0}
          />
          <PrintProgress
            progress={printer.status?.progress ?? 0}
            layer={printer.status?.current_layer}
            totalLayers={printer.status?.total_layers}
            eta={printer.status?.eta}
            fileName={printer.status?.current_file}
          />
        </div>
        <div className="printer-col-right">
          <PrinterControls
            printing={printer.status?.state === 'printing'}
            onStart={printer.startPrint}
            onStop={printer.stopPrint}
            onUpload={printer.uploadFile}
          />
          <PrinterFileList
            files={printer.files}
            onStartFile={printer.startPrint}
            loading={printer.loading}
          />
        </div>
      </div>
    </div>
  )
}
