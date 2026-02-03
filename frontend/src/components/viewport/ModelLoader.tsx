import { useEffect, useRef } from 'react'
import { useLoader, useThree } from '@react-three/fiber'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import * as THREE from 'three'

interface ModelLoaderProps {
  url: string
  type: string
  wireframe: boolean
}

function STLModel({ url, wireframe }: { url: string; wireframe: boolean }) {
  const geometry = useLoader(STLLoader, url)
  const meshRef = useRef<THREE.Mesh>(null)
  const { camera } = useThree()

  useEffect(() => {
    if (meshRef.current && geometry) {
      geometry.computeBoundingBox()
      const box = geometry.boundingBox!
      const center = new THREE.Vector3()
      box.getCenter(center)
      geometry.translate(-center.x, -center.y, -center.z)

      const size = new THREE.Vector3()
      box.getSize(size)
      const maxDim = Math.max(size.x, size.y, size.z)
      const scale = 4 / maxDim
      meshRef.current.scale.setScalar(scale)

      if ('position' in camera) {
        (camera as THREE.PerspectiveCamera).position.set(5, 5, 5)
        camera.lookAt(0, 0, 0)
      }
    }
  }, [geometry, camera])

  return (
    <mesh ref={meshRef} geometry={geometry} castShadow receiveShadow>
      <meshStandardMaterial
        color="#06B6D4"
        wireframe={wireframe}
        metalness={0.3}
        roughness={0.6}
      />
    </mesh>
  )
}

function OBJModel({ url, wireframe }: { url: string; wireframe: boolean }) {
  const obj = useLoader(OBJLoader, url)
  const groupRef = useRef<THREE.Group>(null)

  useEffect(() => {
    if (groupRef.current) {
      const box = new THREE.Box3().setFromObject(groupRef.current)
      const center = new THREE.Vector3()
      box.getCenter(center)
      groupRef.current.position.sub(center)

      const size = new THREE.Vector3()
      box.getSize(size)
      const maxDim = Math.max(size.x, size.y, size.z)
      if (maxDim > 0) groupRef.current.scale.setScalar(4 / maxDim)
    }
  }, [obj])

  useEffect(() => {
    obj.traverse((child) => {
      if ((child as THREE.Mesh).isMesh) {
        const mesh = child as THREE.Mesh
        if (mesh.material) {
          (mesh.material as THREE.MeshStandardMaterial).wireframe = wireframe
        }
      }
    })
  }, [obj, wireframe])

  return <primitive ref={groupRef} object={obj} />
}

function GLTFModel({ url, wireframe }: { url: string; wireframe: boolean }) {
  const gltf = useLoader(GLTFLoader, url)
  const groupRef = useRef<THREE.Group>(null)

  useEffect(() => {
    if (groupRef.current) {
      const box = new THREE.Box3().setFromObject(groupRef.current)
      const center = new THREE.Vector3()
      box.getCenter(center)
      groupRef.current.position.sub(center)

      const size = new THREE.Vector3()
      box.getSize(size)
      const maxDim = Math.max(size.x, size.y, size.z)
      if (maxDim > 0) groupRef.current.scale.setScalar(4 / maxDim)
    }
  }, [gltf])

  useEffect(() => {
    gltf.scene.traverse((child) => {
      if ((child as THREE.Mesh).isMesh) {
        const mesh = child as THREE.Mesh
        if (mesh.material) {
          (mesh.material as THREE.MeshStandardMaterial).wireframe = wireframe
        }
      }
    })
  }, [gltf, wireframe])

  return <primitive ref={groupRef} object={gltf.scene} />
}

export function ModelLoader({ url, type, wireframe }: ModelLoaderProps) {
  const ext = type.toLowerCase()
  if (ext === 'stl') return <STLModel url={url} wireframe={wireframe} />
  if (ext === 'obj') return <OBJModel url={url} wireframe={wireframe} />
  if (ext === 'gltf' || ext === 'glb') return <GLTFModel url={url} wireframe={wireframe} />
  return null
}
