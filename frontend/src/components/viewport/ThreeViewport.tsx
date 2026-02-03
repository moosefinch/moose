import { Suspense, useRef, useEffect } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Grid, Environment } from '@react-three/drei'
import { ModelLoader } from './ModelLoader'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'

interface ThreeViewportProps {
  modelUrl: string | null
  modelType: string
  wireframe: boolean
  showGrid: boolean
  resetKey: number
}

export function ThreeViewport({ modelUrl, modelType, wireframe, showGrid, resetKey }: ThreeViewportProps) {
  const controlsRef = useRef<OrbitControlsImpl>(null)

  useEffect(() => {
    if (controlsRef.current) {
      controlsRef.current.reset()
    }
  }, [resetKey])

  return (
    <div className="viewport-canvas-wrapper">
      <Canvas
        camera={{ position: [5, 5, 5], fov: 50 }}
        style={{ width: '100%', height: '100%' }}
      >
        <ambientLight intensity={0.4} />
        <directionalLight position={[10, 10, 5]} intensity={0.8} castShadow />
        <directionalLight position={[-5, 5, -5]} intensity={0.3} />

        {showGrid && (
          <Grid
            args={[20, 20]}
            cellSize={1}
            cellThickness={0.5}
            cellColor="#333333"
            sectionSize={5}
            sectionThickness={1}
            sectionColor="#555555"
            fadeDistance={30}
            fadeStrength={1}
            followCamera={false}
            infiniteGrid
          />
        )}

        <Suspense fallback={null}>
          {modelUrl && (
            <ModelLoader url={modelUrl} type={modelType} wireframe={wireframe} />
          )}
        </Suspense>

        <OrbitControls
          ref={controlsRef}
          enableDamping
          dampingFactor={0.1}
          minDistance={0.5}
          maxDistance={100}
        />
        <Environment preset="warehouse" background={false} />
      </Canvas>

      {!modelUrl && (
        <div className="viewport-empty-overlay">
          <p>No model loaded</p>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Use the toolbar to open an STL, OBJ, or glTF file
          </p>
        </div>
      )}
    </div>
  )
}
