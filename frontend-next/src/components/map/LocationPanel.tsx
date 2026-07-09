import { useMemo } from 'react'
import { Search, X, Phone, MapPin } from 'lucide-react'
import {
  allCategories,
  categoryConfig,
  type LocationCategory,
  type MapLocation,
} from '@/data/map-locations'
import { cn } from '@/lib/utils'

interface LocationPanelProps {
  /** 经筛选+搜索后的地点列表（由父组件传入） */
  locations: MapLocation[]
  /** 全部地点数量（用于"全部"徽标计数） */
  totalCount: number
  /** 当前激活的类别筛选（null = 全部） */
  activeCategory: LocationCategory | null
  onCategoryChange: (cat: LocationCategory | null) => void
  /** 搜索关键词 */
  searchKeyword: string
  onSearchChange: (kw: string) => void
  /** 当前选中的地点 id */
  selectedLocationId: string | null
  onSelectLocation: (id: string | null) => void
  /** 触发飞行到指定地点 */
  onFlyTo: (id: string) => void
}

/**
 * 左侧地点管理面板
 * - 类别筛选
 * - 名称搜索
 * - 地点列表（点击飞行）
 * - 选中地点详情卡片
 */
export default function LocationPanel({
  locations,
  totalCount,
  activeCategory,
  onCategoryChange,
  searchKeyword,
  onSearchChange,
  selectedLocationId,
  onSelectLocation,
  onFlyTo,
}: LocationPanelProps) {
  // 当前选中的地点对象
  const selected = useMemo(
    () => locations.find((l) => l.id === selectedLocationId) ?? null,
    [locations, selectedLocationId],
  )

  const handleItemClick = (id: string) => {
    onSelectLocation(id)
    onFlyTo(id)
  }

  return (
    <div className="flex h-full w-full flex-col bg-white">
      {/* 顶部：搜索 */}
      <div className="border-b border-gray-100 p-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={searchKeyword}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="搜索地点名称..."
            className="w-full rounded-xl border border-gray-200 bg-gray-50 py-2 pl-9 pr-9 text-sm text-gray-800 placeholder-gray-400 transition focus:border-blue-500 focus:bg-white focus:outline-none"
          />
          {searchKeyword && (
            <button
              type="button"
              onClick={() => onSearchChange('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              aria-label="清空搜索"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* 类别筛选 */}
      <div className="flex flex-wrap gap-1.5 border-b border-gray-100 p-3">
        <CategoryChip
          active={activeCategory === null}
          onClick={() => onCategoryChange(null)}
          label="全部"
          count={totalCount}
        />
        {allCategories.map((cat) => {
          const cfg = categoryConfig[cat]
          const count = locations.filter((l) => l.category === cat).length
          return (
            <CategoryChip
              key={cat}
              active={activeCategory === cat}
              onClick={() => onCategoryChange(cat)}
              label={cfg.label}
              color={cfg.color}
              count={count}
            />
          )
        })}
      </div>

      {/* 地点列表 */}
      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {locations.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center px-4 text-center">
            <MapPin className="mb-2 h-8 w-8 text-gray-300" />
            <p className="text-sm text-gray-400">未找到匹配的地点</p>
            <p className="mt-1 text-xs text-gray-300">
              尝试更换筛选条件或清空搜索
            </p>
          </div>
        ) : (
          <ul className="space-y-1">
            {locations.map((loc) => {
              const cfg = categoryConfig[loc.category]
              const isActive = loc.id === selectedLocationId
              return (
                <li key={loc.id}>
                  <button
                    type="button"
                    onClick={() => handleItemClick(loc.id)}
                    className={cn(
                      'group flex w-full items-start gap-2.5 rounded-xl px-3 py-2.5 text-left transition',
                      isActive
                        ? 'bg-blue-50 ring-1 ring-blue-200'
                        : 'hover:bg-gray-50',
                    )}
                  >
                    <span
                      className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-bold text-white"
                      style={{ background: cfg.color }}
                    >
                      {cfg.label[0]}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span
                        className={cn(
                          'block truncate text-sm font-medium',
                          isActive ? 'text-blue-700' : 'text-gray-800',
                        )}
                      >
                        {loc.name}
                      </span>
                      <span className="mt-0.5 line-clamp-1 block text-xs text-gray-500">
                        {loc.address}
                      </span>
                    </span>
                    <span
                      className="mt-0.5 shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium"
                      style={{
                        background: `${cfg.color}1a`,
                        color: cfg.color,
                      }}
                    >
                      {cfg.label}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      {/* 选中地点详情卡片 */}
      {selected && (
        <div className="border-t border-gray-100 bg-gray-50/60 p-3">
          <div className="rounded-xl bg-white p-3 shadow-sm ring-1 ring-gray-100">
            <div className="mb-2 flex items-start justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <span
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white"
                  style={{ background: categoryConfig[selected.category].color }}
                >
                  {categoryConfig[selected.category].label[0]}
                </span>
                <h3 className="truncate text-sm font-semibold text-gray-900">
                  {selected.name}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => onSelectLocation(null)}
                className="shrink-0 rounded-full p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
                aria-label="关闭详情"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>

            <div className="space-y-1.5 text-xs">
              <div className="flex items-start gap-1.5 text-gray-600">
                <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gray-400" />
                <span className="flex-1 break-words">{selected.address}</span>
              </div>
              {selected.phone && (
                <div className="flex items-center gap-1.5 text-gray-600">
                  <Phone className="h-3.5 w-3.5 shrink-0 text-gray-400" />
                  <span>{selected.phone}</span>
                </div>
              )}
            </div>

            {selected.description && (
              <p className="mt-2 border-t border-gray-100 pt-2 text-xs leading-relaxed text-gray-500">
                {selected.description}
              </p>
            )}

            <button
              type="button"
              onClick={() => onFlyTo(selected.id)}
              className="mt-3 w-full rounded-lg bg-blue-600 py-1.5 text-xs font-medium text-white transition hover:bg-blue-700"
            >
              飞行到此地点
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/** 类别筛选 chip */
function CategoryChip({
  active,
  onClick,
  label,
  color,
  count,
}: {
  active: boolean
  onClick: () => void
  label: string
  color?: string
  count: number
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition',
        active
          ? 'bg-gray-900 text-white'
          : 'bg-gray-100 text-gray-600 hover:bg-gray-200',
      )}
    >
      {color && (
        <span
          className="h-2 w-2 rounded-full"
          style={{ background: color }}
        />
      )}
      <span>{label}</span>
      <span
        className={cn(
          'rounded-full px-1 text-[10px]',
          active ? 'bg-white/20 text-white' : 'bg-gray-200 text-gray-500',
        )}
      >
        {count}
      </span>
    </button>
  )
}
