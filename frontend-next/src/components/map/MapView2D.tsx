import { useEffect, useRef } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import {
  categoryConfig,
  type MapLocation,
  type LocationCategory,
} from '@/data/map-locations'

// OpenFreeMap 平面模式样式（无需 API Key，完全免费开源）
// positron：浅色简洁，类似 Apple Map 浅色风格，加载快速
const MAP_STYLE_URL = 'https://tiles.openfreemap.org/styles/positron'

// 默认中心：上海
const DEFAULT_CENTER: [number, number] = [121.4737, 31.2304]
const DEFAULT_ZOOM = 12

/** 分类图标字符（与 MapView3D 保持一致） */
const categoryIconChar: Record<LocationCategory, string> = {
  law_firm: '律',
  court: '法',
  police: '警',
  labor_bureau: '劳',
  other: '·',
}

// marker 与 popup 的样式（与 MapView3D 共用同一套样式定义）
const INJECTED_STYLE = `
.lvsh-map-marker{
  display:flex;align-items:center;justify-content:center;
  border-radius:50% 50% 50% 0;transform:rotate(-45deg);
  border:2px solid #fff;cursor:pointer;padding:0;
  transition:width .15s,height .15s,box-shadow .15s;
  background:linear-gradient(135deg,var(--mc),var(--mb));
}
.lvsh-map-marker:hover{transform:rotate(-45deg) scale(1.08);}
.lvsh-map-marker__inner{
  transform:rotate(45deg);color:#fff;font-weight:700;
  font-size:12px;line-height:1;letter-spacing:-1px;
  font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  user-select:none;
}
.lvsh-popup{min-width:220px;max-width:280px;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;}
.lvsh-popup__head{display:flex;align-items:center;gap:8px;margin-bottom:8px;}
.lvsh-popup__badge{
  display:inline-block;font-size:11px;font-weight:600;color:#fff;
  padding:2px 8px;border-radius:10px;border:1px solid rgba(0,0,0,.08);
  white-space:nowrap;
}
.lvsh-popup__title{font-size:14px;font-weight:700;color:#1f2937;flex:1;word-break:break-word;}
.lvsh-popup__row{display:flex;gap:6px;margin:4px 0;font-size:12px;line-height:1.5;}
.lvsh-popup__row--desc{margin-top:6px;padding-top:6px;border-top:1px solid #f3f4f6;}
.lvsh-popup__label{color:#9ca3af;flex-shrink:0;width:30px;}
.lvsh-popup__value{color:#374151;flex:1;word-break:break-word;}
`

/** 视图状态：经纬度中心 + 缩放 */
export interface MapViewSnapshot {
  center: [number, number]
  zoom: number
}

interface MapView2DProps {
  locations: MapLocation[]
  selectedLocationId: string | null
  onSelectLocation: (id: string | null) => void
  /** 当 nonce 变化时，飞行到 id 对应地点 */
  flyTarget: { id: string; nonce: number } | null
  /** 初始视图（用于模式切换时保持中心/缩放），仅首次初始化生效 */
  initialView?: MapViewSnapshot
  /** 地图移动结束时回调，用于上报当前视图状态 */
  onViewChange?: (view: MapViewSnapshot) => void
}

/**
 * 平面地图组件 - OpenFreeMap positron 样式
 * 纯 2D，不启用 terrain / 3D 建筑，加载快速
 */
export default function MapView2D({
  locations,
  selectedLocationId,
  onSelectLocation,
  flyTarget,
  initialView,
  onViewChange,
}: MapView2DProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  // 用稳定的回调引用避免重建 marker / 重复绑定
  const onSelectRef = useRef(onSelectLocation)
  onSelectRef.current = onSelectLocation
  const onViewChangeRef = useRef(onViewChange)
  onViewChangeRef.current = onViewChange
  // 仅在首次初始化时读取 initialView，避免后续变更导致重建
  const initialViewRef = useRef<MapViewSnapshot | undefined>(initialView)

  // 初始化地图（仅一次）
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const init = initialViewRef.current
    const center = init?.center ?? DEFAULT_CENTER
    const zoom = init?.zoom ?? DEFAULT_ZOOM

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE_URL,
      center,
      zoom,
      // 平面模式：禁止倾斜与旋转，保持纯 2D 视角
      pitch: 0,
      bearing: 0,
      maxPitch: 0,
      dragRotate: false,
      touchPitch: false,
      attributionControl: { compact: true },
      canvasContextAttributes: { antialias: true },
    })

    mapRef.current = map

    // 缩放按钮（不显示指南针，平面模式无需旋转）
    map.addControl(
      new maplibregl.NavigationControl({
        visualizePitch: false,
        showZoom: true,
        showCompass: false,
      }),
      'top-right',
    )
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left')

    // 上报当前视图状态（模式切换时用于保持中心/缩放）
    const reportView = () => {
      const c = map.getCenter()
      onViewChangeRef.current?.({
        center: [c.lng, c.lat],
        zoom: map.getZoom(),
      })
    }
    map.on('moveend', reportView)
    map.once('load', reportView)

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // 渲染地点 marker（locations 变化时重建）
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const markers: maplibregl.Marker[] = []

    const renderMarkers = () => {
      markers.forEach((m) => m.remove())
      markers.length = 0

      locations.forEach((loc) => {
        const cfg = categoryConfig[loc.category]
        const isSelected = loc.id === selectedLocationId
        const size = isSelected ? 38 : 30

        const el = document.createElement('button')
        el.type = 'button'
        el.className = 'lvsh-map-marker'
        el.setAttribute('aria-label', loc.name)
        el.style.width = `${size}px`
        el.style.height = `${size}px`
        el.style.setProperty('--mc', cfg.color)
        el.style.setProperty('--mb', cfg.borderColor)
        el.style.boxShadow = isSelected
          ? '0 4px 14px rgba(0,0,0,0.35)'
          : '0 2px 6px rgba(0,0,0,0.25)'
        el.style.zIndex = isSelected ? '10' : '1'
        el.innerHTML = `<span class="lvsh-map-marker__inner">${categoryIconChar[loc.category]}</span>`

        el.addEventListener('click', (ev) => {
          ev.stopPropagation()
          onSelectRef.current(loc.id)
        })

        const marker = new maplibregl.Marker({
          element: el,
          anchor: 'bottom',
        })
          .setLngLat([loc.lng, loc.lat])
          .setPopup(
            new maplibregl.Popup({ offset: 24, closeButton: false }).setHTML(
              renderPopupHtml(loc),
            ),
          )
          .addTo(map)

        markers.push(marker)
      })
    }

    if (map.loaded()) {
      renderMarkers()
    } else {
      map.once('load', renderMarkers)
    }

    return () => {
      markers.forEach((m) => m.remove())
      markers.length = 0
    }
  }, [locations, selectedLocationId])

  // 点击地图空白处取消选中
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const handler = () => onSelectRef.current(null)
    map.on('click', handler)
    return () => {
      map.off('click', handler)
    }
  }, [])

  // 外部触发飞行（panel 点击列表项）
  useEffect(() => {
    const map = mapRef.current
    if (!map || !flyTarget) return
    const target = locations.find((l) => l.id === flyTarget.id)
    if (!target) return

    const fly = () => {
      map.flyTo({
        center: [target.lng, target.lat],
        zoom: Math.max(map.getZoom(), 15.5),
        // 平面模式：保持 2D 视角
        pitch: 0,
        bearing: 0,
        speed: 1.2,
        curve: 1.6,
        essential: true,
      })
    }

    if (map.loaded()) {
      fly()
    } else {
      map.once('load', fly)
    }
    // 仅依赖 nonce 变化触发
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flyTarget?.nonce])

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: INJECTED_STYLE }} />
      <div ref={containerRef} className="h-full w-full" />
    </>
  )
}

/** 生成 popup HTML（地点详情卡片，与 MapView3D 保持一致） */
function renderPopupHtml(loc: MapLocation): string {
  const cfg = categoryConfig[loc.category]
  const phoneHtml = loc.phone
    ? `<div class="lvsh-popup__row"><span class="lvsh-popup__label">电话</span><span class="lvsh-popup__value">${escapeHtml(loc.phone)}</span></div>`
    : ''
  const descHtml = loc.description
    ? `<div class="lvsh-popup__row lvsh-popup__row--desc"><span class="lvsh-popup__value">${escapeHtml(loc.description)}</span></div>`
    : ''
  return `
    <div class="lvsh-popup">
      <div class="lvsh-popup__head">
        <span class="lvsh-popup__badge" style="background:${cfg.color};border-color:${cfg.borderColor};">${cfg.label}</span>
        <span class="lvsh-popup__title">${escapeHtml(loc.name)}</span>
      </div>
      <div class="lvsh-popup__body">
        <div class="lvsh-popup__row"><span class="lvsh-popup__label">地址</span><span class="lvsh-popup__value">${escapeHtml(loc.address)}</span></div>
        ${phoneHtml}
        ${descHtml}
      </div>
    </div>
  `
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}
