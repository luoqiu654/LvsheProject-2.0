import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { Map as MapIcon, Layers, Box, Zap, RotateCw } from 'lucide-react'
import MapView3D from '@/components/map/MapView3D'
import MapView2D, { type MapViewSnapshot } from '@/components/map/MapView2D'
import MapViewAmap from '@/components/map/MapViewAmap'
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
  // 旋转信号：每次点击"旋转 180°"递增 nonce，触发地图组件 useEffect
  const [rotateSignal, setRotateSignal] = useState<{ nonce: number }>({
    nonce: 0,
  })
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

  // 一键 180° 3D 视角旋转（仅 amap / 3d 模式可用）
  const handleRotate180 = useCallback(() => {
    setRotateSignal((prev) => ({ nonce: prev.nonce + 1 }))
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

        {/* 180° 3D 视角旋转：仅 amap / 3d 模式显示（2D 无 3D 透视，旋转意义不大） */}
        {(mapMode === 'amap' || mapMode === '3d') && (
          <button
            type="button"
            onClick={handleRotate180}
            className="flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-3 py-1 text-xs font-medium text-gray-700 shadow-sm transition hover:bg-gray-50 hover:text-gray-900"
            aria-label="旋转 180°"
            title="旋转 180°"
          >
            <RotateCw className="h-3.5 w-3.5" />
            <span>旋转 180°</span>
          </button>
        )}
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
            <MapViewAmap {...commonMapProps} rotateSignal={rotateSignal} />
          ) : mapMode === '2d' ? (
            <MapView2D {...commonMapProps} />
          ) : (
            <MapView3D {...commonMapProps} rotateSignal={rotateSignal} />
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
