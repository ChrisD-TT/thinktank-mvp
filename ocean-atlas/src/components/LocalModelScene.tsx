import { Float, OrbitControls } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'

import { useAtlasStore } from '../store/useAtlasStore'

function TrenchModel() {
  return (
    <group rotation={[-0.35, 0.2, 0]}>
      <mesh position={[0, 0.75, 0]}>
        <boxGeometry args={[3.8, 0.3, 2.6]} />
        <meshStandardMaterial color="#0d2337" />
      </mesh>
      <mesh position={[0, -0.75, 0]}>
        <coneGeometry args={[1.1, 2.7, 4, 1, true]} />
        <meshStandardMaterial color="#133b5c" wireframe={false} />
      </mesh>
      <mesh position={[0, -0.3, 0]} rotation={[0, Math.PI / 4, 0]}>
        <octahedronGeometry args={[0.32, 0]} />
        <meshStandardMaterial color="#7bdff2" emissive="#4cc9f0" emissiveIntensity={0.8} />
      </mesh>
    </group>
  )
}

function BasinModel() {
  return (
    <group rotation={[-0.55, 0.4, 0]}>
      <mesh>
        <cylinderGeometry args={[1.8, 2.6, 1.8, 32, 1, true]} />
        <meshStandardMaterial color="#12304f" side={2} />
      </mesh>
      <mesh position={[0, -0.35, 0]}>
        <cylinderGeometry args={[1.35, 1.6, 0.5, 32]} />
        <meshStandardMaterial color="#3a86ff" emissive="#1f5fa8" emissiveIntensity={0.55} />
      </mesh>
    </group>
  )
}

function ZoneModel() {
  return (
    <group rotation={[-0.3, 0.6, 0]}>
      <mesh>
        <ringGeometry args={[0.95, 1.85, 64]} />
        <meshBasicMaterial color="#c77dff" transparent opacity={0.65} side={2} />
      </mesh>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.4, 0.12, 16, 120]} />
        <meshStandardMaterial color="#7b2cbf" emissive="#c77dff" emissiveIntensity={0.35} />
      </mesh>
    </group>
  )
}

function CurrentModel() {
  return (
    <group rotation={[-0.8, 0.2, 0.15]}>
      <mesh>
        <torusKnotGeometry args={[1.1, 0.18, 180, 24, 2, 3]} />
        <meshStandardMaterial color="#72efdd" emissive="#72efdd" emissiveIntensity={0.4} />
      </mesh>
    </group>
  )
}

function PointModel() {
  return (
    <group>
      <mesh>
        <icosahedronGeometry args={[1.1, 0]} />
        <meshStandardMaterial color="#4cc9f0" emissive="#4cc9f0" emissiveIntensity={0.45} wireframe />
      </mesh>
    </group>
  )
}

function ModelGeometry() {
  const atlasData = useAtlasStore((state) => state.atlasData)
  const selectedLocationId = useAtlasStore((state) => state.selectedLocationId)
  const location = atlasData.locations.find((item) => item.id === selectedLocationId)
  const modelType = location?.visualization?.modelType ?? 'point'

  switch (modelType) {
    case 'trench':
      return <TrenchModel />
    case 'basin':
      return <BasinModel />
    case 'zone':
      return <ZoneModel />
    case 'point':
      if (location?.type === 'whirlpool') {
        return <CurrentModel />
      }
      return <PointModel />
    default:
      return <PointModel />
  }
}

export function LocalModelScene() {
  return (
    <div className="local-model-card">
      <div className="local-model-copy">
        <p className="eyebrow">Local model</p>
        <h2>Stylized formation view</h2>
        <p>
          A lightweight preview of the selected trench, basin, current field, or mystery zone.
          This is the placeholder for deeper seafloor meshes and cutaway terrain models.
        </p>
      </div>

      <div className="local-model-canvas">
        <Canvas camera={{ position: [0, 0, 4.6], fov: 42 }}>
          <color attach="background" args={['#03101a']} />
          <ambientLight intensity={0.7} />
          <directionalLight position={[3, 4, 5]} intensity={1.2} color="#c6eeff" />
          <directionalLight position={[-4, -3, -2]} intensity={0.4} color="#72efdd" />
          <Float speed={1.3} rotationIntensity={0.2} floatIntensity={0.25}>
            <ModelGeometry />
          </Float>
          <OrbitControls enablePan={false} minDistance={3.2} maxDistance={6.2} autoRotate autoRotateSpeed={0.8} />
        </Canvas>
      </div>
    </div>
  )
}
