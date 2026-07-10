import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { Map as MapIcon, Layers, Box, Zap } from 'lucide-react'
import MapView3D from '@/components/map/MapView3D'
import MapView2D, { type MapViewSnapshot } from '@/components/map/MapView2D'
import MapViewAmap from '@/components/map/MapViewAmap'
import MapRotationDial from '@/components/map/MapRotationDial'
import LocationPanel from '@/components/map/LocationPanel'
import {
  mapLocations,
  type LocationCategory,
} from '@/data/map-locations'
import { cn } from '@/lib/utils'

type MapMode = 'amap' | '2d' | '3d'

/** 默认视图快照（上海，与子组件默认值一致） */
const DEFAULT_VIEW: MapViewSnapshot = {
  center: [121.4737, 31.2304],
  zoom: 12,
}

/** 模式 -> 中文标签（用于顶部副标题展示） */
const MODE_LABEL: Record<MapMode, string> = {
  amap: '高德快速视图',
  '2d': '平面视图',
  '3d': '3D 视图',
}

/**
 * 地图浏览主页面
 * 布局：左侧地点管理面板（320px） + 右侧地图（三模式可切换）
 * 默认高德快速模式（国内 CDN，加载流畅，自带 3D 建筑），
 * 可切换至平面模式（OpenFreeMap）或 3D 模式（MapTiler terrain DEM）。
 */
export default function MapView() {
  const [activeCategory, setActiveCategory] = useState<LocationCategory | null>(
    null,
  )
  const [searchKeyword, setSearchKeyword] = useState('')
  const [selectedLocationId, setSelectedLocationId] = useState<string | null>(
    null,
  )
  // 飞行信号：每次飞行递增 nonce 以触发地图组件的 useEffect
  const [flyTarget, setFlyTarget] = useState<{
    id: string
    nonce: number
  } | null>(null)
  // 旋转拨盘：bearing 为当前角度（0-360），bearingNonce 变化触发地图组件 useEffect
  const [bearing, setBearing] = useState<number>(0)
  const [bearingNonce, setBearingNonce] = useState<number>(0)
  // 俯视角度：pitch 为当前角度（0-60），pitchNonce 变化触发地图组件 useEffect
  const [pitch, setPitch] = useState<number>(45)
  const [pitchNonce, setPitchNonce] = useState<number>(0)
  // 地图模式：默认高德快速模式（国内 CDN，加载流畅，自带 3D 建筑）
  const [mapMode, setMapMode] = useState<MapMode>('amap')
  // 当前视图快照：模式切换时用于保持中心/缩放
  const [currentView, setCurrentView] = useState<MapViewSnapshot>(DEFAULT_VIEW)

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

  // 拨盘旋转：拖动时实时更新 bearing 并递增 nonce 触发地图跟随
  const handleBearingChange = useCallback((angle: number) => {
    // 规范化到 0-360
    const n = angle % 360
    const normalized = n < 0 ? n + 360 : n
    setBearing(normalized)
    setBearingNonce((prev) => prev + 1)
  }, [])

  // 俯视角度滑块：更新 pitch 并递增 nonce 触发地图跟随
  const handlePitchChange = useCallback((p: number) => {
    // 限制到 0-60
    const clamped = Math.max(0, Math.min(60, p))
    setPitch(clamped)
    setPitchNonce((prev) => prev + 1)
  }, [])

  const handleSelectLocation = useCallback((id: string | null) => {
    setSelectedLocationId(id)
  }, [])

  const handleViewChange = useCallback((view: MapViewSnapshot) => {
    setCurrentView(view)
  }, [])

  // 切换地图时保持当前选中状态与飞行信号
  const handleModeChange = useCallback((mode: MapMode) => {
    setMapMode(mode)
  }, [])

  // 地图组件通用 props（三种模式共用）
  const commonMapProps = {
    locations: filteredLocations,
    selectedLocationId,
    onSelectLocation: handleSelectLocation,
    flyTarget,
    initialView: currentView,
    onViewChange: handleViewChange,
  }

  return (
    <div className="flex h-full flex-col overflow-hidden bg-gray-50">
      {/* 顶部标题栏 */}
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-gray-200 bg-white px-4">
        <MapIcon className="h-4 w-4 text-blue-600" />
        <h1 className="text-sm font-semibold text-gray-800">地图浏览</h1>
        <span className="text-xs text-gray-400">
          · {mapLocations.length} 个地点 · {MODE_LABEL[mapMode]}
        </span>

        {/* 模式切换：segmented control（三种模式） */}
        <div className="ml-auto flex items-center rounded-lg bg-gray-100 p-0.5">
          <ModeButton
            active={mapMode === 'amap'}
            onClick={() => handleModeChange('amap')}
            icon={<Zap className="h-3.5 w-3.5" />}
            label="高德快速"
          />
          <ModeButton
            active={mapMode === '2d'}
            onClick={() => handleModeChange('2d')}
            icon={<Layers className="h-3.5 w-3.5" />}
            label="平面"
          />
          <ModeButton
            active={mapMode === '3d'}
            onClick={() => handleModeChange('3d')}
            icon={<Box className="h-3.5 w-3.5" />}
            label="3D"
          />
        </div>
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
          {mapMode === 'amap' ? (
            <>
              <MapViewAmap
                {...commonMapProps}
                bearing={bearing}
                bearingNonce={bearingNonce}
                pitch={pitch}
                pitchNonce={pitchNonce}
              />
              <MapRotationDial
                bearing={bearing}
                onChange={handleBearingChange}
                onReset={() => handleBearingChange(0)}
                pitch={pitch}
                onPitchChange={handlePitchChange}
              />
            </>
          ) : mapMode === '2d' ? (
            <MapView2D {...commonMapProps} />
          ) : (
            <>
              <MapView3D
                {...commonMapProps}
                bearing={bearing}
                bearingNonce={bearingNonce}
                pitch={pitch}
                pitchNonce={pitchNonce}
              />
              <MapRotationDial
                bearing={bearing}
                onChange={handleBearingChange}
                onReset={() => handleBearingChange(0)}
                pitch={pitch}
                onPitchChange={handlePitchChange}
              />
            </>
          )}
        </main>
      </div>
    </div>
  )
}

/** 模式切换按钮（segmented control 子项） */
function ModeButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean
  onClick: () => void
  icon: ReactNode
  label: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition',
        active
          ? 'bg-white text-gray-900 shadow-sm'
          : 'text-gray-500 hover:text-gray-700',
      )}
      aria-pressed={active}
    >
      {icon}
      <span>{label}</span>
    </button>
  )
}
