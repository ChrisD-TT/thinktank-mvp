import { create } from 'zustand'

import type { AtlasDataset } from '../types/atlas'
import { defaultAtlasData } from '../data/defaultAtlas'

type AtlasStore = {
  atlasData: AtlasDataset
  dataSource: 'default' | 'remote'
  dataSourceUrl?: string
  selectedLocationId: string
  selectedLayer: 'all' | 'trenches' | 'wildlife' | 'mystery'
  setAtlasData: (payload: {
    data: AtlasDataset
    source: 'default' | 'remote'
    sourceUrl?: string
  }) => void
  setSelectedLocationId: (id: string) => void
  setSelectedLayer: (layer: AtlasStore['selectedLayer']) => void
}

export const useAtlasStore = create<AtlasStore>((set) => ({
  atlasData: defaultAtlasData,
  dataSource: 'default',
  dataSourceUrl: undefined,
  selectedLocationId: defaultAtlasData.locations[0]?.id ?? '',
  selectedLayer: 'all',
  setAtlasData: ({ data, source, sourceUrl }) =>
    set((state) => {
      const currentSelectionExists = data.locations.some(
        (location) => location.id === state.selectedLocationId,
      )

      return {
        atlasData: data,
        dataSource: source,
        dataSourceUrl: sourceUrl,
        selectedLocationId: currentSelectionExists
          ? state.selectedLocationId
          : (data.locations[0]?.id ?? ''),
      }
    }),
  setSelectedLocationId: (id) => set({ selectedLocationId: id }),
  setSelectedLayer: (layer) => set({ selectedLayer: layer }),
}))
