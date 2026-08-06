export type TruthLevel = 'observed' | 'inferred' | 'speculative'

export type GeoPoint = {
  lat: number
  lng: number
}

export type Environment = {
  temperatureC?: [number, number]
  pressureMpa?: number
  salinityPsu?: [number, number]
  lightLevel?: 'photic' | 'dysphotic' | 'aphotic'
  terrain?: string[]
}

export type Scores = {
  mystery: number
  biodiversity: number
  exploration: number
  extremity: number
}

export type VisualizationConfig = {
  modelType?: 'point' | 'trench' | 'basin' | 'zone'
  depthScale?: number
  colorTheme?: string
}

export type AtlasLocationType =
  | 'trench'
  | 'whirlpool'
  | 'brine-pool'
  | 'blue-hole'
  | 'vent-field'
  | 'mystery-zone'
  | 'abyssal-plain'
  | 'gyre'

export type AtlasLocation = {
  id: string
  name: string
  type: AtlasLocationType
  ocean: string
  region: string
  coordinates: GeoPoint
  depthM?: number
  environment?: Environment
  truthLevel: TruthLevel
  summary: {
    short: string
    scientific?: string
    speculative?: string
  }
  speciesRefs: string[]
  featureRefs: string[]
  eventRefs: string[]
  scores: Scores
  visualization?: VisualizationConfig
}

export type Species = {
  id: string
  name: string
  category: 'fish' | 'mammal' | 'crustacean' | 'microbe' | 'coral' | 'invertebrate'
  status: TruthLevel
  habitatTags: string[]
  depthRangeM?: [number, number]
  facts: {
    diet?: string[]
    adaptations?: string[]
  }
}

export type Feature = {
  id: string
  name: string
  category: 'geology' | 'current' | 'anomaly' | 'ecosystem'
  status: TruthLevel
  description: string
}

export type Event = {
  id: string
  name: string
  type: 'expedition' | 'historical-mystery' | 'discovery'
  date?: string
  confidence: 'high' | 'medium' | 'contested'
  summary: string
}

export type AtlasDataset = {
  locations: AtlasLocation[]
  species: Species[]
  features: Feature[]
  events: Event[]
}
