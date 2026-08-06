import { useEffect, useState } from 'react'

import './App.css'
import { GlobeScene } from './components/GlobeScene'
import { LocalModelScene } from './components/LocalModelScene'
import { LocationPanel } from './components/LocationPanel'
import { loadAtlasData } from './lib/atlasLoader'
import { useAtlasStore } from './store/useAtlasStore'

function App() {
  const setAtlasData = useAtlasStore((state) => state.setAtlasData)
  const dataSource = useAtlasStore((state) => state.dataSource)
  const dataSourceUrl = useAtlasStore((state) => state.dataSourceUrl)
  const [loadingState, setLoadingState] = useState<'loading' | 'ready'>('loading')

  useEffect(() => {
    let active = true

    loadAtlasData().then((payload) => {
      if (!active) {
        return
      }

      setAtlasData(payload)
      setLoadingState('ready')
    })

    return () => {
      active = false
    }
  }, [setAtlasData])

  return (
    <main className="app-shell">
      <section className="hero-copy">
        <p className="eyebrow">Abyss Atlas</p>
        <h1>Explore trenches, wildlife, mystery zones, and deep-ocean extremes.</h1>
        <p className="hero-text">
          A stylized 3D globe for exploring curated ocean locations with observed facts,
          inferred habitat clues, and clearly labeled speculative models.
        </p>
        <div className="status-row">
          <span className="status-pill">{loadingState === 'loading' ? 'Loading atlas…' : 'Atlas ready'}</span>
          <span className="status-pill muted">
            {dataSource === 'remote' ? 'Remote dataset active' : 'Bundled fallback active'}
          </span>
          {dataSourceUrl ? <span className="status-url">{dataSourceUrl}</span> : null}
        </div>
      </section>

      <section className="content-grid">
        <div className="left-column">
          <GlobeScene />
          <div className="dual-panels">
            <LocalModelScene />
            <div className="info-strip">
              <div>
                <span>Focus</span>
                <strong>Curated ocean atlas</strong>
              </div>
              <div>
                <span>Modes</span>
                <strong>Observed · Inferred · Speculative</strong>
              </div>
              <div>
                <span>Next</span>
                <strong>Trench meshes · anomaly overlays · wildlife depth cards</strong>
              </div>
            </div>
          </div>
        </div>

        <LocationPanel />
      </section>
    </main>
  )
}

export default App
