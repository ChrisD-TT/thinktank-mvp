import { OrbitControls, Sphere, Stars } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { useMemo } from 'react'
import * as THREE from 'three'

import { useAtlasStore } from '../store/useAtlasStore'
import type { AtlasLocation } from '../types/atlas'

const EARTH_RADIUS = 2.2

function latLngToVector3(lat: number, lng: number, radius: number) {
  const phi = ((90 - lat) * Math.PI) / 180
  const theta = ((lng + 180) * Math.PI) / 180

  return new THREE.Vector3(
    -(radius * Math.sin(phi) * Math.cos(theta)),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  )
}

function getMarkerColor(location: AtlasLocation) {
  switch (location.type) {
    case 'trench':
      return '#4cc9f0'
    case 'whirlpool':
      return '#90e0ef'
    case 'brine-pool':
      return '#72efdd'
    case 'blue-hole':
      return '#3a86ff'
    case 'mystery-zone':
      return '#c77dff'
    default:
      return '#7bdff2'
  }
}

function GlobeMarkers() {
  const atlasData = useAtlasStore((state) => state.atlasData)
  const selectedLocationId = useAtlasStore((state) => state.selectedLocationId)
  const selectedLayer = useAtlasStore((state) => state.selectedLayer)
  const setSelectedLocationId = useAtlasStore((state) => state.setSelectedLocationId)

  const filteredLocations = useMemo(() => {
    if (selectedLayer === 'trenches') {
      return atlasData.locations.filter((location) => location.type === 'trench')
    }

    if (selectedLayer === 'wildlife') {
      return atlasData.locations.filter((location) => location.speciesRefs.length > 0)
    }

    if (selectedLayer === 'mystery') {
      return atlasData.locations.filter(
        (location) =>
          location.type === 'mystery-zone' || location.truthLevel === 'speculative',
      )
    }

    return atlasData.locations
  }, [selectedLayer])

  return filteredLocations.map((location) => {
    const position = latLngToVector3(
      location.coordinates.lat,
      location.coordinates.lng,
      EARTH_RADIUS + 0.08,
    )
    const isSelected = location.id === selectedLocationId

    return (
      <mesh
        key={location.id}
        position={position}
        onClick={() => setSelectedLocationId(location.id)}
      >
        <sphereGeometry args={[isSelected ? 0.09 : 0.06, 18, 18]} />
        <meshStandardMaterial
          color={isSelected ? '#ffffff' : getMarkerColor(location)}
          emissive={getMarkerColor(location)}
          emissiveIntensity={isSelected ? 1.4 : 0.7}
        />
      </mesh>
    )
  })
}

function GlobeShell() {
  return (
    <group>
      <Sphere args={[EARTH_RADIUS, 64, 64]}>
        <meshStandardMaterial
          color="#07121d"
          emissive="#0f2742"
          emissiveIntensity={0.7}
          metalness={0.15}
          roughness={0.85}
        />
      </Sphere>

      <mesh>
        <sphereGeometry args={[EARTH_RADIUS + 0.03, 64, 64]} />
        <meshStandardMaterial
          color="#12304f"
          transparent
          opacity={0.16}
          side={THREE.DoubleSide}
        />
      </mesh>

      <mesh rotation={[0.25, -0.4, 0.1]}>
        <torusGeometry args={[2.75, 0.01, 12, 180]} />
        <meshBasicMaterial color="#103556" transparent opacity={0.55} />
      </mesh>
    </group>
  )
}

export function GlobeScene() {
  return (
    <div className="scene-card">
      <Canvas camera={{ position: [0, 0, 6.5], fov: 45 }}>
        <color attach="background" args={['#02070d']} />
        <ambientLight intensity={0.55} />
        <directionalLight position={[4, 3, 5]} intensity={1.6} color="#9bd2ff" />
        <directionalLight position={[-5, -2, -4]} intensity={0.55} color="#4cc9f0" />
        <Stars radius={80} depth={40} count={2500} factor={3} saturation={0} fade speed={0.4} />

        <GlobeShell />
        <GlobeMarkers />

        <OrbitControls
          enablePan={false}
          minDistance={4.2}
          maxDistance={9}
          autoRotate
          autoRotateSpeed={0.35}
        />
      </Canvas>

      <div className="scene-legend">
        <span><i className="legend-dot trench"></i>Trenches</span>
        <span><i className="legend-dot wildlife"></i>Wildlife</span>
        <span><i className="legend-dot mystery"></i>Mystery zones</span>
      </div>
    </div>
  )
}
