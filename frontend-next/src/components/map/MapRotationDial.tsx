import { useCallback, useEffect, useRef, useState } from 'react'

interface MapRotationDialProps {
  /** 当前角度 0-360 */
  bearing: number
  /** 拖动/点击触发角度变更 */
  onChange: (angle: number) => void
  /** 重置朝北（点击中心按钮） */
  onReset?: () => void
}

/** 规范化角度到 0-360 */
function normalizeAngle(deg: number): number {
  const n = deg % 360
  return n < 0 ? n + 360 : n
}

/**
 * 可拖动 360° 旋转拨盘控件
 *
 - 圆形 SVG + 指针，拖动实时回调 onChange(angle)
 - 使用 pointer 事件统一 mouse / touch
 - 拖动事件 stopPropagation 避免与地图原生拖拽冲突
 - 绝对定位地图右上角，毛玻璃风格
 */
export default function MapRotationDial({
  bearing,
  onChange,
  onReset,
}: MapRotationDialProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [dragging, setDragging] = useState(false)
  // 拖动期间的本地角度（避免每次回调往返导致指针跳动）
  const [dragAngle, setDragAngle] = useState<number | null>(null)

  const displayAngle = dragAngle ?? bearing

  // 计算指针角度（基于鼠标位置相对于圆心）
  const calcAngle = useCallback((clientX: number, clientY: number) => {
    const svg = svgRef.current
    if (!svg) return 0
    const rect = svg.getBoundingClientRect()
    const cx = rect.left + rect.width / 2
    const cy = rect.top + rect.height / 2
    // atan2 返回 -PI~PI，0 朝东（+x），顺时针递增到 +y（南）
    // 我们让 0° = 北（向上），顺时针递增
    const rad = Math.atan2(clientY - cy, clientX - cx)
    const deg = (rad * 180) / Math.PI + 90
    return normalizeAngle(deg)
  }, [])

  // pointerdown：开始拖动
  const handlePointerDown = useCallback(
    (e: React.PointerEvent<SVGSVGElement>) => {
      e.stopPropagation()
      e.preventDefault()
      try {
        ;(e.target as Element).setPointerCapture?.(e.pointerId)
      } catch {
        // 忽略 setPointerCapture 异常（部分浏览器在特殊节点上不支持）
      }
      setDragging(true)
      const ang = calcAngle(e.clientX, e.clientY)
      setDragAngle(ang)
      onChange(Math.round(ang))
    },
    [calcAngle, onChange],
  )

  // pointermove：实时更新角度
  const handlePointerMove = useCallback(
    (e: React.PointerEvent<SVGSVGElement>) => {
      if (!dragging) return
      e.stopPropagation()
      const ang = calcAngle(e.clientX, e.clientY)
      setDragAngle(ang)
      onChange(Math.round(ang))
    },
    [dragging, calcAngle, onChange],
  )

  // pointerup / pointerleave / pointercancel：结束拖动
  const handlePointerEnd = useCallback(
    (e: React.PointerEvent<SVGSVGElement>) => {
      if (!dragging) return
      e.stopPropagation()
      try {
        ;(e.target as Element).releasePointerCapture?.(e.pointerId)
      } catch {
        // 忽略
      }
      setDragging(false)
      // 保留 dragAngle 直至下次外部 bearing 更新（useEffect 会同步）
    },
    [dragging],
  )

  // 外部 bearing 变化时（非拖动）同步本地角度
  useEffect(() => {
    if (!dragging) {
      setDragAngle(null)
    }
  }, [bearing, dragging])

  // SVG 尺寸
  const size = 96
  const center = size / 2
  const radius = center - 6
  // 指针角度（0° 朝北 = 12 点钟方向）
  const pointerAngle = displayAngle

  // 生成 12 个刻度（每 30°）
  const ticks = Array.from({ length: 12 }, (_, i) => {
    const ang = i * 30
    const rad = ((ang - 90) * Math.PI) / 180
    const inner = radius - 6
    const outer = radius
    return {
      ang,
      x1: center + inner * Math.cos(rad),
      y1: center + inner * Math.sin(rad),
      x2: center + outer * Math.cos(rad),
      y2: center + outer * Math.sin(rad),
      major: ang % 90 === 0,
    }
  })

  // 方位标识（N/E/S/W）
  const cardinal = [
    { label: 'N', ang: 0 },
    { label: 'E', ang: 90 },
    { label: 'S', ang: 180 },
    { label: 'W', ang: 270 },
  ].map((c) => {
    const rad = ((c.ang - 90) * Math.PI) / 180
    const r = radius - 14
    return {
      ...c,
      x: center + r * Math.cos(rad),
      y: center + r * Math.sin(rad),
    }
  })

  // 指针终点
  const pointerRad = ((pointerAngle - 90) * Math.PI) / 180
  const pointerLen = radius - 18
  const pointerX = center + pointerLen * Math.cos(pointerRad)
  const pointerY = center + pointerLen * Math.sin(pointerRad)

  return (
    <div
      className="pointer-events-none absolute right-4 top-4 z-20 flex select-none flex-col items-center gap-1"
      role="group"
      aria-label="地图旋转控件"
    >
      <div
        className="pointer-events-auto relative flex flex-col items-center rounded-full border border-white/40 bg-white/25 p-1 shadow-lg backdrop-blur-md"
        style={{ width: size, height: size }}
      >
        <svg
          ref={svgRef}
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          className="block cursor-grab touch-none active:cursor-grabbing"
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerEnd}
          onPointerCancel={handlePointerEnd}
          onPointerLeave={handlePointerEnd}
          role="slider"
          aria-label="旋转角度"
          aria-valuemin={0}
          aria-valuemax={360}
          aria-valuenow={Math.round(displayAngle)}
          aria-valuetext={`方位 ${Math.round(displayAngle)} 度`}
          tabIndex={0}
        >
          {/* 外圈背景 */}
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="rgba(255,255,255,0.18)"
            stroke="rgba(255,255,255,0.55)"
            strokeWidth={1}
          />
          {/* 内圈 */}
          <circle
            cx={center}
            cy={center}
            r={radius - 12}
            fill="rgba(31,41,55,0.35)"
            stroke="rgba(255,255,255,0.2)"
            strokeWidth={0.5}
          />
          {/* 刻度 */}
          {ticks.map((t) => (
            <line
              key={t.ang}
              x1={t.x1}
              y1={t.y1}
              x2={t.x2}
              y2={t.y2}
              stroke={t.major ? '#ffffff' : 'rgba(255,255,255,0.6)'}
              strokeWidth={t.major ? 1.5 : 0.8}
              strokeLinecap="round"
            />
          ))}
          {/* 方位字母 */}
          {cardinal.map((c) => (
            <text
              key={c.label}
              x={c.x}
              y={c.y}
              textAnchor="middle"
              dominantBaseline="middle"
              fontSize={9}
              fontWeight={c.label === 'N' ? 700 : 500}
              fill={c.label === 'N' ? '#fbbf24' : '#ffffff'}
              style={{ userSelect: 'none' }}
            >
              {c.label}
            </text>
          ))}
          {/* 指针 */}
          <line
            x1={center}
            y1={center}
            x2={pointerX}
            y2={pointerY}
            stroke="#fbbf24"
            strokeWidth={2.5}
            strokeLinecap="round"
          />
          {/* 指针尖端小圆 */}
          <circle cx={pointerX} cy={pointerY} r={2.5} fill="#fbbf24" />
          {/* 中心圆 */}
          <circle cx={center} cy={center} r={4} fill="#ffffff" />
          <circle
            cx={center}
            cy={center}
            r={2}
            fill={dragging ? '#fbbf24' : '#1f2937'}
          />
        </svg>
      </div>

      {/* 角度数值 + 重置按钮 */}
      <div className="pointer-events-auto flex items-center gap-1 rounded-md bg-white/25 px-2 py-0.5 text-[10px] font-medium text-white shadow-sm backdrop-blur-md">
        <span>方位 {Math.round(displayAngle)}°</span>
        {onReset && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onReset()
            }}
            className="ml-1 rounded px-1 text-white/80 transition hover:text-white"
            aria-label="重置朝北"
            title="重置朝北"
          >
            ⟲
          </button>
        )}
      </div>
    </div>
  )
}
