import { useEffect, useRef } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import {
  categoryConfig,
  type MapLocation,
  type LocationCategory,
} from '@/data/map-locations'

// MapTiler 配置（Key 设计为前端可见，非私密 key）
const MAPTILER_KEY = 'BRVGk2DhuQUmnSvnZIRU'
const MAP_STYLE_URL = `https://api.maptiler.com/maps/hybrid/style.json?key=${MAPTILER_KEY}`
const TERRAIN_TILES_URL = `https://api.maptiler.com/tiles/terrain-rgb/tiles.json?key=${MAPTILER_KEY}`

// 默认中心：上海
const DEFAULT_CENTER: [number, number] = [121.4737, 31.2304]
const DEFAULT_ZOOM = 12.5
const DEFAULT_PITCH = 45
const DEFAULT_BEARING = 0

/** 分类图标字符（Apple Map 风格的圆形标记中显示） */
const categoryIconChar: Record<LocationCategory, string> = {
  law_firm: '律',
  court: '法',
  police: '警',
  labor_bureau: '劳',
  other: '·',
}

// marker 与 popup 的样式（注入到 <head>，避免污染全局 CSS 文件）
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

interface MapView3DProps {
  locations: MapLocation[]
  selectedLocationId: string | null
  onSelectLocation: (id: string | null) => void
  /** 当 nonce 变化时，飞行到 id 对应地点 */
  flyTarget: { id: string; nonce: number } | null
  /** 当前目标方位角 0-360（由外部拨盘控制） */
  bearing?: number
  /** 当 nonce 变化时，应用 bearing 到地图视角 */
  bearingNonce?: number
  /** 当前俯视角度 0-60（由外部拨盘控制） */
  pitch?: number
  /** 当 nonce 变化时，应用 pitch 到地图视角 */
  pitchNonce?: number
  /** 初始视图（用于模式切换时保持中心/缩放），仅首次初始化生效 */
  initialView?: { center: [number, number]; zoom: number }
  /** 地图移动结束时回调，用于上报当前视图状态 */
  onViewChange?: (view: { center: [number, number]; zoom: number }) => void
}

/**
 * 3D 地图组件 - Apple Map 风格
 * 使用 maplibre-gl 原生 API + MapTiler hybrid 样式 + 3D 地形 + 3D 建筑
 */
export default function MapView3D({
  locations,
  selectedLocationId,
  onSelectLocation,
  flyTarget,
  bearing,
  bearingNonce,
  pitch,
  pitchNonce,
  initialView,
  onViewChange,
}: MapView3DProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  // 用一个稳定的回调引用避免重建 marker
  const onSelectRef = useRef(onSelectLocation)
  onSelectRef.current = onSelectLocation
  const onViewChangeRef = useRef(onViewChange)
  onViewChangeRef.current = onViewChange
  // 仅在首次初始化时读取 initialView，避免后续变更导致重建
  const initialViewRef = useRef(initialView)

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
      pitch: DEFAULT_PITCH,
      bearing: DEFAULT_BEARING,
      attributionControl: { compact: true },
      canvasContextAttributes: { antialias: true },
    })

    mapRef.current = map

    map.addControl(
      new maplibregl.NavigationControl({
        visualizePitch: true,
        showZoom: true,
        showCompass: true,
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

    map.on('style.load', () => {
      // 1) 添加 3D 地形 DEM 源并启用
      try {
        if (!map.getSource('terrainSource')) {
          map.addSource('terrainSource', {
            type: 'raster-dem',
            url: TERRAIN_TILES_URL,
            tileSize: 512,
          })
        }
        map.setTerrain({ source: 'terrainSource', exaggeration: 1.5 })
      } catch (err) {
        // 静默：地形加载失败不影响地图主体
        console.warn('[MapView3D] terrain load failed:', err)
      }

      // 2) 添加 3D 建筑图层（zoom>=14 显示）
      try {
        const layers = map.getStyle()?.layers ?? []
        const labelLayer = layers.find(
          (l) =>
            l.type === 'symbol' &&
            (l.layout as { [k: string]: unknown } | undefined)?.[
              'text-field'
            ] !== undefined,
        )

        if (!map.getLayer('3d-buildings')) {
          map.addLayer(
            {
              id: '3d-buildings',
              source: 'composite',
              'source-layer': 'building',
              filter: ['==', 'extrude', 'true'],
              type: 'fill-extrusion',
              minzoom: 14,
              paint: {
                'fill-extrusion-color': '#d4d4d8',
                'fill-extrusion-height': ['get', 'height'],
                'fill-extrusion-base': ['get', 'min_height'],
                'fill-extrusion-opacity': 0.7,
              },
            },
            labelLayer ? labelLayer.id : undefined,
          )
        }
      } catch (err) {
        // MapTiler hybrid 样式自带 3D 建筑，自定义图层加载失败可忽略
        console.info('[MapView3D] custom 3d-buildings layer skipped:', err)
      }
    })

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
        pitch: 60,
        bearing: map.getBearing(),
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

  // 外部拨盘触发视角旋转（即时跟随，无动画过渡以贴合拖动手感）
  useEffect(() => {
    const map = mapRef.current
    if (!map || bearing === undefined || bearingNonce === undefined) return
    // 初始 nonce=0 跳过（首次渲染，避免覆盖地图初始 bearing）
    if (bearingNonce === 0) return

    const applyBearing = () => {
      try {
        // maplibre setBearing(bearing) 为即时设置（无动画），贴合拖动手感
        map.setBearing(bearing as number)
      } catch (err) {
        console.warn('[MapView3D] setBearing failed:', err)
      }
    }

    if (map.loaded()) {
      applyBearing()
    } else {
      map.once('load', applyBearing)
    }
    // 仅依赖 nonce 变化触发
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bearingNonce])

  // 外部拨盘触发俯视角度变化（即时跟随，与 bearing 模式一致）
  useEffect(() => {
    const map = mapRef.current
    if (!map || pitch === undefined || pitchNonce === undefined) return
    // 初始 nonce=0 跳过（避免覆盖地图初始 pitch）
    if (pitchNonce === 0) return

    const applyPitch = () => {
      try {
        map.setPitch(pitch as number)
      } catch (err) {
        console.warn('[MapView3D] setPitch failed:', err)
      }
    }

    if (map.loaded()) {
      applyPitch()
    } else {
      map.once('load', applyPitch)
    }
    // 仅依赖 nonce 变化触发
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pitchNonce])

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: INJECTED_STYLE }} />
      <div ref={containerRef} className="h-full w-full" />
    </>
  )
}

/** 生成 popup HTML（地点详情卡片） */
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
