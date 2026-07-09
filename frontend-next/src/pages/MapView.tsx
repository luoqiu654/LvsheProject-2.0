import { useCallback, useMemo, useState } from 'react'
import { Map as MapIcon } from 'lucide-react'
import MapView3D from '@/components/map/MapView3D'
import LocationPanel from '@/components/map/LocationPanel'
import {
  mapLocations,
  type LocationCategory,
} from '@/data/map-locations'

/**
 * 地图浏览主页面
 * 布局：左侧地点管理面板（320px） + 右侧 3D 地图
 */
export default function MapView() {
  const [activeCategory, setActiveCategory] = useState<LocationCategory | null>(
    null,
  )
  const [searchKeyword, setSearchKeyword] = useState('')
  const [selectedLocationId, setSelectedLocationId] = useState<string | null>(
    null,
  )
  // 飞行信号：每次飞行递增 nonce 以触发 MapView3D 的 useEffect
  const [flyTarget, setFlyTarget] = useState<{
    id: string
    nonce: number
  } | null>(null)

  // 筛选 + 搜索
  const filteredLocations = useMemo(() => {
    const kw = searchKeyword.trim().toLowerCase()
    return mapLocations.filter((loc) => {
      if (activeCategory && loc.category !== activeCategory) return false
      if (kw) {
        const haystack = `${loc.name} ${loc.address} ${loc.description ?? ''}`.toLowerCase()
        if (!haystack.includes(kw)) return false
      }
      return true
    })
  }, [activeCategory, searchKeyword])

  const handleFlyTo = useCallback((id: string) => {
    setFlyTarget((prev) => ({ id, nonce: (prev?.nonce ?? 0) + 1 }))
  }, [])

  const handleSelectLocation = useCallback((id: string | null) => {
    setSelectedLocationId(id)
  }, [])

  return (
    <div className="flex h-full flex-col overflow-hidden bg-gray-50">
      {/* 顶部标题栏 */}
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-gray-200 bg-white px-4">
        <MapIcon className="h-4 w-4 text-blue-600" />
        <h1 className="text-sm font-semibold text-gray-800">地图浏览</h1>
        <span className="text-xs text-gray-400">
          · {mapLocations.length} 个地点 · Apple Map 风格 3D 视图
        </span>
      </header>

      {/* 主体：左面板 + 右地图 */}
      <div className="flex min-h-0 flex-1">
        <aside className="w-80 shrink-0 border-r border-gray-200">
          <LocationPanel
            locations={filteredLocations}
            totalCount={mapLocations.length}
            activeCategory={activeCategory}
            onCategoryChange={setActiveCategory}
            searchKeyword={searchKeyword}
            onSearchChange={setSearchKeyword}
            selectedLocationId={selectedLocationId}
            onSelectLocation={handleSelectLocation}
            onFlyTo={handleFlyTo}
          />
        </aside>
        <main className="relative min-w-0 flex-1">
          <MapView3D
            locations={filteredLocations}
            selectedLocationId={selectedLocationId}
            onSelectLocation={handleSelectLocation}
            flyTarget={flyTarget}
          />
        </main>
      </div>
    </div>
  )
}
