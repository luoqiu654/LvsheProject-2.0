import { useEffect, useRef, useState } from "react"
import {
  Brain,
  ChevronDown,
  Eye,
  Loader2,
  type LucideIcon,
} from "lucide-react"
import { cn } from "@/lib/utils"

// 可折叠的"思考过程/分析过程"面板
// 用于：
//   1. AI 回复前的思考过程（步骤列表，蓝色基调）
//   2. 用户消息下的 AI 视觉分析卡片（单段文本/children，紫色基调）
interface ThinkingPanelProps {
  // 思考步骤列表（列表形式展示）；与 content/children 二选一
  steps?: string[]
  // 单段文本内容（段落形式展示，如流式 reasoning_content）
  content?: string
  // 自定义内容（与 steps/content 二选一，如视觉分析描述）
  children?: React.ReactNode
  // 自定义标题；不传则按展开/收起动态显示
  title?: string
  // 是否正在思考中（true 时强制展开并显示加载动画）
  active?: boolean
  // 是否正在思考中（active 的别名，向后兼容）
  isThinking?: boolean
  // 初始是否展开
  defaultExpanded?: boolean
  // 标题图标，默认 Brain；vision 变体默认 Eye
  icon?: LucideIcon
  // 视觉分析样式（紫色基调）vs 思考样式（蓝色基调）
  variant?: "thinking" | "vision"
  // 可选自定义类名
  className?: string
}

export function ThinkingPanel({
  steps,
  content,
  children,
  title,
  active = false,
  isThinking,
  defaultExpanded,
  icon,
  variant = "thinking",
  className,
}: ThinkingPanelProps) {
  const thinking = active || !!isThinking
  const [expanded, setExpanded] = useState(defaultExpanded ?? thinking)
  // 记录上一次的 thinking 状态，用于检测 true→false 的转变
  const wasThinking = useRef(thinking)

  // 思考开始时自动展开；思考结束时自动折叠（用户可手动展开）
  useEffect(() => {
    if (thinking) {
      setExpanded(true)
    } else if (wasThinking.current) {
      // 仅在 thinking 从 true 变为 false 时自动折叠
      // 避免影响 defaultExpanded 的初始展开（如视觉分析卡片）
      setExpanded(false)
    }
    wasThinking.current = thinking
  }, [thinking])

  const hasSteps = !!steps && steps.length > 0
  const hasContent = hasSteps || !!content || !!children
  if (!hasContent) return null

  const Icon: LucideIcon = icon ?? (variant === "vision" ? Eye : Brain)

  // 标题：优先使用传入的 title；否则按展开状态动态显示
  const headerTitle =
    title ?? (expanded || thinking ? "AI思考中..." : "查看AI思考过程")

  const isVision = variant === "vision"

  return (
    <div
      className={cn(
        "mb-2 overflow-hidden rounded-lg border backdrop-blur-sm",
        isVision
          ? "border-purple-100 bg-purple-50/60"
          : "border-blue-100 bg-blue-50/60",
        className,
      )}
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className={cn(
          "flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium transition",
          isVision
            ? "text-purple-700 hover:bg-purple-100/50"
            : "text-blue-700 hover:bg-blue-100/50",
        )}
      >
        {thinking ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Icon className="h-3.5 w-3.5" />
        )}
        <span className="flex-1 truncate">{headerTitle}</span>
        {hasSteps && (
          <span
            className={cn(
              "text-[10px]",
              isVision ? "text-purple-400" : "text-blue-400",
            )}
          >
            {steps!.length} 步
          </span>
        )}
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 transition-transform",
            expanded && "rotate-180",
          )}
        />
      </button>
      {expanded && (
        <div
          className={cn(
            "border-t px-3 py-2 text-xs leading-relaxed text-gray-600",
            isVision ? "border-purple-100" : "border-blue-100",
          )}
        >
          {hasSteps ? (
            <ol className="space-y-1">
              {steps!.map((s, i) => (
                <li key={i} className="flex gap-1.5">
                  <span
                    className={cn(
                      "shrink-0",
                      isVision ? "text-purple-400" : "text-blue-400",
                    )}
                  >
                    ›
                  </span>
                  <span className="whitespace-pre-wrap">{s}</span>
                </li>
              ))}
            </ol>
          ) : content ? (
            <p className="whitespace-pre-wrap break-words">{content}</p>
          ) : (
            children
          )}
        </div>
      )}
    </div>
  )
}

export default ThinkingPanel
