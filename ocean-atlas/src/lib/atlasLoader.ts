import type { AtlasDataset } from '../types/atlas'
import { defaultAtlasData } from '../data/defaultAtlas'

const atlasUrl = import.meta.env.VITE_ATLAS_DATA_URL?.trim()

export type AtlasSource = 'default' | 'remote'

export type LoadedAtlas = {
  data: AtlasDataset
  source: AtlasSource
  sourceUrl?: string
}

function isAtlasDataset(value: unknown): value is AtlasDataset {
  if (!value || typeof value !== 'object') {
    return false
  }

  const candidate = value as Partial<AtlasDataset>

  return (
    Array.isArray(candidate.locations) &&
    Array.isArray(candidate.species) &&
    Array.isArray(candidate.features) &&
    Array.isArray(candidate.events)
  )
}

export async function loadAtlasData(): Promise<LoadedAtlas> {
  if (!atlasUrl) {
    return { data: defaultAtlasData, source: 'default' }
  }

  try {
    const response = await fetch(atlasUrl, {
      headers: {
        Accept: 'application/json',
      },
    })

    if (!response.ok) {
      throw new Error(`Atlas request failed with ${response.status}`)
    }

    const payload = (await response.json()) as unknown

    if (!isAtlasDataset(payload)) {
      throw new Error('Atlas payload is not a valid dataset shape')
    }

    return {
      data: payload,
      source: 'remote',
      sourceUrl: atlasUrl,
    }
  } catch (error) {
    console.warn('Falling back to bundled atlas data.', error)

    return {
      data: defaultAtlasData,
      source: 'default',
      sourceUrl: atlasUrl,
    }
  }
}
