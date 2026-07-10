import { useEffect, useRef, useState } from 'react'
import {
  categoryConfig,
  type MapLocation,
  type LocationCategory,
} from '@/data/map-locations'

// 高德地图 JS API 2.0 配置
// Key 设计为前端可见（与 MapTiler key 一致，非私密 key）
const AMAP_KEY = '5943ccb982ce72509b2839775332f1ea'
const AMAP_SECURITY_CODE = 'cb80ad78aa17da23ebf358c383d198b6'
const AMAP_SCRIPT_SRC = `https://webapi.amap.com/maps?v=2.0&key=${AMAP_KEY}&plugin=AMap.Scale,AMap.ToolBar`
const AMAP_SCRIPT_ATTR = 'data-amap-loader'

// 默认中心：上海（[lng, lat]，与高德坐标顺序一致）
const DEFAULT_CENTER: [number, number] = [121.4737, 31.2304]
const DEFAULT_ZOOM = 12
const DEFAULT_PITCH = 45

/** 分类图标字符（与 MapView2D/3D 保持一致） */
const categoryIconChar: Record<LocationCategory, string> = {
  law_firm: '律',
  court: '法',
  police: '警',
  labor_bureau: '劳',
  other: '·',
}

// marker 与 popup 的样式（与 MapView2D/3D 共用同一套样式定义）
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
/* 高德 InfoWindow 默认内容白底，需清除默认内边距以贴合自定义卡片 */
.amap-info-content{padding:0 !important;}
.amap-info-sharp,.amap-info-close{display:none !important;}
`

interface MapViewAmapProps {
  locations: MapLocation[]
  selectedLocationId: string | null
  onSelectLocation: (id: string | null) => void
  /** 当 nonce 变化时，飞行到 id 对应地点 */
  flyTarget: { id: string; nonce: number } | null
  /** 当前目标方位角 0-360（由外部拨盘控制） */
  bearing?: number
  /** 当 nonce 变化时，应用 bearing 到地图视角 */
  bearingNonce?: number
  /** 初始视图（用于模式切换时保持中心/缩放），仅首次初始化生效 */
  initialView?: { center: [number, number]; zoom: number }
  /** 地图移动结束时回调，用于上报当前视图状态 */
  onViewChange?: (view: { center: [number, number]; zoom: number }) => void
}

/**
 * 高德地图组件 - 3D 快速模式
 * 通过动态 script 加载高德 JS API 2.0，国内访问流畅，自带 3D 建筑渲染。
 * 接口与 MapView2D/MapView3D 保持一致。
 */
export default function MapViewAmap({
  locations,
  selectedLocationId,
  onSelectLocation,
  flyTarget,
  bearing,
  bearingNonce,
  initialView,
  onViewChange,
}: MapViewAmapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  // 高德地图实例（any：JS API 通过 CDN 注入，无 TS 类型声明）
  const mapRef = useRef<any>(null)
  const infoWindowRef = useRef<any>(null)
  const markersRef = useRef<any[]>([])
  // 用稳定的回调引用避免重建 marker / 重复绑定
  const onSelectRef = useRef(onSelectLocation)
  onSelectRef.current = onSelectLocation
  const onViewChangeRef = useRef(onViewChange)
  onViewChangeRef.current = onViewChange
  // 仅在首次初始化时读取 initialView，避免后续变更导致重建
  const initialViewRef = useRef(initialView)
  // 地图是否就绪（脚本加载完成 + 实例创建完成）
  const [mapReady, setMapReady] = useState(false)
  // 拨盘旋转 rAF 节流句柄（避免高频回调卡顿）
  const rafIdRef = useRef<number | null>(null)

  // 初始化地图（仅一次）
  useEffect(() => {
    if (!containerRef.current) return

    let disposed = false
    let map: any = null

    const initMap = () => {
      const AMap = (window as any).AMap
      if (!AMap || !containerRef.current || disposed) return

      const init = initialViewRef.current
      const center = init?.center ?? DEFAULT_CENTER
      // maplibre zoom 与高德 zoom 量级相近，直接复用
      const zoom = init?.zoom ?? DEFAULT_ZOOM

      try {
        map = new AMap.Map(containerRef.current, {
          viewMode: '3D',
          zoom,
          center,
          pitch: DEFAULT_PITCH,
          resizeEnable: true,
        })
      } catch (err) {
        console.error('[MapViewAmap] map init failed:', err)
        return
      }

      mapRef.current = map

      // 控件：比例尺 + 工具条
      try {
        map.addControl(new AMap.Scale())
        map.addControl(new AMap.ToolBar({ position: 'RT' }))
      } catch (err) {
        console.warn('[MapViewAmap] control add failed:', err)
      }

      // 共享 InfoWindow
      infoWindowRef.current = new AMap.InfoWindow({
        offset: new AMap.Pixel(0, -34),
        closeWhenClickMap: true,
      })

      // 上报当前视图状态（模式切换时用于保持中心/缩放）
      const reportView = () => {
        if (!mapRef.current) return
        const c = mapRef.current.getCenter()
        onViewChangeRef.current?.({
          center: [c.getLng(), c.getLat()],
          zoom: mapRef.current.getZoom(),
        })
      }
      map.on('moveend', reportView)
      map.on('zoomend', reportView)
      // 首次加载后上报一次
      map.on('complete', reportView)

      // 点击地图空白处取消选中
      map.on('click', () => {
        onSelectRef.current(null)
      })

      setMapReady(true)
    }

    // 设置安全密钥（必须在加载 JS API 之前设置）
    ;(window as any)._AMapSecurityConfig = {
      securityJsCode: AMAP_SECURITY_CODE,
    }

    if ((window as any).AMap) {
      initMap()
    } else {
      // 避免重复注入脚本：若已有同名 script 标签则复用其 load 事件
      const existing = document.querySelector<HTMLScriptElement>(
        `script[${AMAP_SCRIPT_ATTR}]`,
      )
      if (existing) {
        if (existing.dataset.loaded === 'true') {
          initMap()
        } else {
          existing.addEventListener('load', () => {
            existing.dataset.loaded = 'true'
            initMap()
          })
          existing.addEventListener('error', () => {
            console.error('[MapViewAmap] amap script load error (existing)')
          })
        }
      } else {
        const script = document.createElement('script')
        script.src = AMAP_SCRIPT_SRC
        script.async = true
        script.setAttribute(AMAP_SCRIPT_ATTR, '')
        script.onload = () => {
          script.dataset.loaded = 'true'
          initMap()
        }
        script.onerror = () => {
          console.error('[MapViewAmap] amap script load error')
        }
        document.head.appendChild(script)
      }
    }

    return () => {
      disposed = true
      // 销毁地图实例与标记
      try {
        markersRef.current.forEach((m) => m?.setMap?.(null))
        markersRef.current = []
        infoWindowRef.current?.close?.()
        map?.destroy?.()
      } catch (err) {
        console.warn('[MapViewAmap] cleanup failed:', err)
      }
      mapRef.current = null
      infoWindowRef.current = null
      setMapReady(false)
    }
  }, [])

  // 渲染地点 marker（locations / selectedLocationId / mapReady 变化时重建）
  useEffect(() => {
    if (!mapReady) return
    const map = mapRef.current
    const AMap = (window as any).AMap
    if (!map || !AMap) return

    // 清除旧 marker
    markersRef.current.forEach((m) => m?.setMap?.(null))
    markersRef.current = []

    const markers: any[] = []

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
        const iw = infoWindowRef.current
        if (iw) {
          iw.setContent(renderPopupHtml(loc))
          iw.open(map, new AMap.LngLat(loc.lng, loc.lat))
        }
        onSelectRef.current(loc.id)
      })

      const marker = new AMap.Marker({
        position: new AMap.LngLat(loc.lng, loc.lat),
        content: el,
        offset: new AMap.Pixel(-size / 2, -size),
        // 选中态提层，确保不被其他 marker 遮挡
        zIndex: isSelected ? 200 : 100,
      })
      marker.setMap(map)
      markers.push(marker)
    })

    markersRef.current = markers
  }, [locations, selectedLocationId, mapReady])

  // 外部触发飞行（panel 点击列表项）
  useEffect(() => {
    if (!mapReady) return
    const map = mapRef.current
    if (!map || !flyTarget) return
    const target = locations.find((l) => l.id === flyTarget.id)
    if (!target) return

    const currentZoom = map.getZoom() ?? DEFAULT_ZOOM
    const targetZoom = Math.max(currentZoom, 15.5)
    try {
      // 高德无原生 flyTo，使用 setZoomAndCenter 平滑过渡
      map.setZoomAndCenter(targetZoom, [target.lng, target.lat], true, () => {
        // 飞行后展开 InfoWindow
        const AMap = (window as any).AMap
        const iw = infoWindowRef.current
        if (iw && AMap) {
          iw.setContent(renderPopupHtml(target))
          iw.open(map, new AMap.LngLat(target.lng, target.lat))
        }
      })
    } catch (err) {
      console.warn('[MapViewAmap] flyTo failed:', err)
    }
    // 仅依赖 nonce 变化触发
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flyTarget?.nonce, mapReady])

  // 外部拨盘触发视角旋转（即时跟随，用 requestAnimationFrame 节流避免卡顿）
  useEffect(() => {
    if (!mapReady) return
    const map = mapRef.current
    if (!map || bearing === undefined || bearingNonce === undefined) return
    // 初始 nonce=0 跳过（首次渲染）
    if (bearingNonce === 0) return

    // 取消上一帧未执行的请求，避免高频回调堆积
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current)
    }
    rafIdRef.current = requestAnimationFrame(() => {
      rafIdRef.current = null
      try {
        // 高德 setRotation 第二参为是否动画过渡，false=即时跟随拖动
        map.setRotation(bearing as number, false)
      } catch (err) {
        console.warn('[MapViewAmap] setRotation failed:', err)
      }
    })
    // 仅依赖 nonce 变化触发
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bearingNonce, mapReady])

  // 组件卸载时清理 rAF
  useEffect(() => {
    return () => {
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current)
        rafIdRef.current = null
      }
    }
  }, [])

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: INJECTED_STYLE }} />
      <div ref={containerRef} className="h-full w-full" />
    </>
  )
}

/** 生成 popup HTML（地点详情卡片，与 MapView2D/3D 保持一致） */
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
