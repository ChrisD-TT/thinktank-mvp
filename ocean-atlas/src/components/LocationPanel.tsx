import { useAtlasStore } from '../store/useAtlasStore'

function formatRange(range?: [number, number], unit?: string) {
  if (!range) {
    return 'Unknown'
  }

  return `${range[0]}–${range[1]}${unit ? ` ${unit}` : ''}`
}

export function LocationPanel() {
  const atlasData = useAtlasStore((state) => state.atlasData)
  const selectedLocationId = useAtlasStore((state) => state.selectedLocationId)
  const setSelectedLayer = useAtlasStore((state) => state.setSelectedLayer)
  const dataSource = useAtlasStore((state) => state.dataSource)

  const location = atlasData.locations.find((item) => item.id === selectedLocationId)

  if (!location) {
    return null
  }

  const relatedSpecies = atlasData.species.filter((species) =>
    location.speciesRefs.includes(species.id),
  )
  const relatedFeatures = atlasData.features.filter((feature) =>
    location.featureRefs.includes(feature.id),
  )
  const relatedEvents = atlasData.events.filter((event) => location.eventRefs.includes(event.id))

  return (
    <aside className="panel-card">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Ocean Atlas</p>
          <h1>{location.name}</h1>
          <p className="panel-subtitle">
            {location.region} · {location.ocean}
          </p>
        </div>
        <span className={`truth-pill ${location.truthLevel}`}>{location.truthLevel}</span>
      </div>

      <p className="panel-summary">{location.summary.short}</p>

      <div className="metrics-grid">
        <div>
          <span>Depth</span>
          <strong>{location.depthM ? `${location.depthM.toLocaleString()} m` : 'Variable'}</strong>
        </div>
        <div>
          <span>Mystery</span>
          <strong>{location.scores.mystery}/100</strong>
        </div>
        <div>
          <span>Biodiversity</span>
          <strong>{location.scores.biodiversity}/100</strong>
        </div>
        <div>
          <span>Exploration</span>
          <strong>{location.scores.exploration}/100</strong>
        </div>
      </div>

      <div className="layer-buttons">
        <button type="button" onClick={() => setSelectedLayer('all')}>
          All
        </button>
        <button type="button" onClick={() => setSelectedLayer('trenches')}>
          Trenches
        </button>
        <button type="button" onClick={() => setSelectedLayer('wildlife')}>
          Wildlife
        </button>
        <button type="button" onClick={() => setSelectedLayer('mystery')}>
          Mystery
        </button>
      </div>

      <section className="panel-section">
        <h2>Environment</h2>
        <ul>
          <li>Temperature: {formatRange(location.environment?.temperatureC, '°C')}</li>
          <li>Pressure: {location.environment?.pressureMpa ?? 'Unknown'} MPa</li>
          <li>Salinity: {formatRange(location.environment?.salinityPsu, 'PSU')}</li>
          <li>Light: {location.environment?.lightLevel ?? 'Unknown'}</li>
          <li>Terrain: {location.environment?.terrain?.join(', ') ?? 'Unknown'}</li>
        </ul>
      </section>

      <section className="panel-section">
        <h2>Known life</h2>
        <div className="chip-list">
          {relatedSpecies.map((species) => (
            <article key={species.id} className="chip-card">
              <h3>{species.name}</h3>
              <p>{species.habitatTags.join(' · ')}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="panel-section">
        <h2>Features</h2>
        <div className="chip-list">
          {relatedFeatures.map((feature) => (
            <article key={feature.id} className="chip-card">
              <h3>{feature.name}</h3>
              <p>{feature.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="panel-section">
        <h2>Expeditions and records</h2>
        <div className="chip-list">
          {relatedEvents.map((event) => (
            <article key={event.id} className="chip-card">
              <h3>{event.name}</h3>
              <p>{event.summary}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="panel-section">
        <h2>Dataset source</h2>
        <div className="chip-card">
          <h3>{dataSource === 'remote' ? 'Google Cloud / remote atlas' : 'Bundled atlas fallback'}</h3>
          <p>
            {dataSource === 'remote'
              ? 'The app is currently reading atlas records from the configured remote JSON endpoint.'
              : 'The app is using the built-in atlas dataset because no remote URL is configured or the remote fetch failed.'}
          </p>
        </div>
      </section>

      <section className="panel-section model-card">
        <h2>Model card</h2>
        <p>
          <strong>Observed:</strong> {location.summary.scientific ?? 'No observed summary yet.'}
        </p>
        <p>
          <strong>Speculative:</strong>{' '}
          {location.summary.speculative ?? 'No speculative model notes yet.'}
        </p>
      </section>
    </aside>
  )
}
