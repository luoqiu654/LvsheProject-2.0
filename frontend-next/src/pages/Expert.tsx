import { useCallback, useEffect, useRef, useState } from "react"
import { Play, Square, RotateCcw, Download, AlertCircle, Loader2, Scale, Gavel } from "lucide-react"
import { streamTrial, type TrialResult, type TrialRole } from "@/api/expert"
import { MarkdownRenderer } from "@/components/shared/MarkdownRenderer"
import { cn } from "@/lib/utils"

// ========== 角色信息 ==========

interface RoleInfo {
  label: string
  emoji: string
  badge: string
  card: string
  header: string
  dot: string
}

const ROLE_INFO: Record<TrialRole, RoleInfo> = {
  chief_judge: {
    label: "审判长",
    emoji: "⚖️",
    badge: "bg-purple-100 text-purple-700",
    card: "border-purple-200 bg-purple-50/50",
    header: "text-purple-800",
    dot: "bg-purple-500",
  },
  plaintiff: {
    label: "原告",
    emoji: "📋",
    badge: "bg-blue-100 text-blue-700",
    card: "border-blue-200 bg-blue-50/50",
    header: "text-blue-800",
    dot: "bg-blue-500",
  },
  defendant: {
    label: "被告",
    emoji: "🛡️",
    badge: "bg-red-100 text-red-700",
    card: "border-red-200 bg-red-50/50",
    header: "text-red-800",
    dot: "bg-red-500",
  },
  judge: {
    label: "法官",
    emoji: "🔍",
    badge: "bg-green-100 text-green-700",
    card: "border-green-200 bg-green-50/50",
    header: "text-green-800",
    dot: "bg-green-500",
  },
  verdict: {
    label: "判决书",
    emoji: "📜",
    badge: "bg-amber-100 text-amber-700",
    card: "border-amber-300 bg-amber-50/50",
    header: "text-amber-800",
    dot: "bg-amber-500",
  },
}

// ========== 发言卡片类型 ==========

interface SpeechCard {
  id: string
  role: TrialRole
  round: number
  content: string
  isComplete: boolean
}

// ========== 示例案件 ==========

const EXAMPLES = [
  "甲方委托乙方开发网站，合同金额50000元。乙方迟迟未交付，合同未明确交付时间，甲方要求解除合同并赔偿损失。",
  "张某向李某借款10万元，约定月利率2%，借款期限1年。到期后张某未还款，李某起诉要求还本付息。",
  "王某在商场购物时因地滑摔倒受伤，花去医疗费3万元。王某要求商场赔偿医疗费、误工费等损失。",
]

const MIN_CASE_LENGTH = 10

// ========== 组件 ==========

export default function Expert() {
  const [caseInput, setCaseInput] = useState("")
  const [rounds, setRounds] = useState(2)
  const [isRunning, setIsRunning] = useState(false)
  const [speeches, setSpeeches] = useState<SpeechCard[]>([])
  const [trialResult, setTrialResult] = useState<TrialResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // 自动滚动到底部
  const scrollToBottom = useCallback(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [speeches, scrollToBottom])

  // 开始庭审
  const handleStart = useCallback(async () => {
    const text = caseInput.trim()
    if (text.length < MIN_CASE_LENGTH || isRunning) return

    setSpeeches([])
    setTrialResult(null)
    setError(null)
    setIsRunning(true)

    const controller = new AbortController()
    abortRef.current = controller

    await streamTrial(
      { case_description: text, rounds },
      {
        signal: controller.signal,
        onEvent: (event) => {
          if (event.event === "speech_start" && event.role !== undefined) {
            setSpeeches((prev) => [
              ...prev,
              {
                id: crypto.randomUUID(),
                role: event.role!,
                round: event.round ?? 0,
                content: "",
                isComplete: false,
              },
            ])
          } else if (event.event === "speech_chunk" && event.text && event.role !== undefined) {
            const role = event.role!
            const round = event.round ?? 0
            setSpeeches((prev) =>
              prev.map((s) =>
                s.role === role && s.round === round && !s.isComplete
                  ? { ...s, content: s.content + event.text }
                  : s,
              ),
            )
          } else if (event.event === "speech_end" && event.role !== undefined) {
            const role = event.role!
            const round = event.round ?? 0
            setSpeeches((prev) =>
              prev.map((s) =>
                s.role === role && s.round === round && !s.isComplete
                  ? { ...s, isComplete: true }
                  : s,
              ),
            )
          } else if (event.event === "done") {
            if (event.result) {
              setTrialResult(event.result)
            }
          } else if (event.event === "error") {
            setError(event.message || "庭审出错")
          }
        },
        onError: (err) => {
          setError(err)
        },
        onDone: () => {
          setIsRunning(false)
          abortRef.current = null
        },
      },
    )

    setIsRunning(false)
    abortRef.current = null
  }, [caseInput, isRunning, rounds])

  // 停止庭审
  const handleStop = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setIsRunning(false)
    // 标记当前未完成的发言为已完成
    setSpeeches((prev) => prev.map((s) => ({ ...s, isComplete: true })))
  }, [])

  // 重置
  const handleReset = useCallback(() => {
    if (isRunning) handleStop()
    setSpeeches([])
    setTrialResult(null)
    setError(null)
    setCaseInput("")
  }, [isRunning, handleStop])

  // 导出庭审记录
  const handleExport = useCallback(() => {
    const result = trialResult
    if (!result) return

    const lines: string[] = []
    lines.push("# 法庭模拟庭审记录")
    lines.push("")
    lines.push(`**庭审ID**: ${result.trial_id}`)
    lines.push(`**创建时间**: ${result.created_at}`)
    lines.push(`**案件**: ${result.case}`)
    lines.push(`**总结**: ${result.summary}`)
    lines.push("")
    lines.push("---")
    lines.push("")
    lines.push("## 审判长开场白")
    lines.push("")
    lines.push(result.opening)
    lines.push("")

    for (const r of result.rounds) {
      lines.push("---")
      lines.push("")
      lines.push(`## 第 ${r.round_number} 轮辩论`)
      lines.push("")
      lines.push("### 原告")
      lines.push("")
      lines.push(r.plaintiff_speech)
      lines.push("")
      lines.push("### 被告")
      lines.push("")
      lines.push(r.defendant_speech)
      lines.push("")
      if (r.judge_inquiry) {
        lines.push("### 法官追问")
        lines.push("")
        lines.push(r.judge_inquiry)
        lines.push("")
      }
    }

    if (result.verdict) {
      lines.push("---")
      lines.push("")
      lines.push("## 最终判决")
      lines.push("")
      lines.push(`**胜诉方**: ${result.verdict.winner}`)
      lines.push(`**原告胜诉概率**: ${result.verdict.plaintiff_win_rate}%`)
      lines.push(`**被告胜诉概率**: ${result.verdict.defendant_win_rate}%`)
      lines.push("")
      lines.push("### 关键胜负点")
      for (const p of result.verdict.key_points) {
        lines.push(`- ${p}`)
      }
      lines.push("")
      lines.push("### 判决理由")
      lines.push(result.verdict.reasoning)
      lines.push("")
      lines.push("### 行动建议")
      for (const s of result.verdict.action_suggestions) {
        lines.push(`- ${s}`)
      }
      lines.push("")
      lines.push("### 判决书全文")
      lines.push("")
      lines.push(result.verdict.full_text)
    }

    const md = lines.join("\n")
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `庭审记录_${result.trial_id}.md`
    a.click()
    URL.revokeObjectURL(url)
  }, [trialResult])

  // 按角色分组发言
  const chiefJudgeSpeeches = speeches.filter((s) => s.role === "chief_judge")
  const plaintiffSpeeches = speeches.filter((s) => s.role === "plaintiff")
  const defendantSpeeches = speeches.filter((s) => s.role === "defendant")
  const judgeSpeeches = speeches.filter((s) => s.role === "judge" || s.role === "verdict")

  const hasStarted = speeches.length > 0 || isRunning
  const canStart = caseInput.trim().length >= MIN_CASE_LENGTH && !isRunning

  return (
    <div className="flex h-full flex-col overflow-hidden bg-gray-50">
      {/* 顶部标题栏 */}
      <div className="shrink-0 border-b border-gray-200 bg-white px-6 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Gavel className="h-5 w-5 text-purple-600" />
            <h1 className="text-lg font-bold text-gray-900">专家会诊 · 法庭模拟</h1>
          </div>
          <div className="flex items-center gap-2">
            {/* 辩论轮数选择 */}
            {!hasStarted && (
              <select
                value={rounds}
                onChange={(e) => setRounds(Number(e.target.value))}
                disabled={isRunning}
                className="rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-700 focus:border-purple-500 focus:outline-none"
                title="辩论轮数"
              >
                <option value={1}>1 轮辩论</option>
                <option value={2}>2 轮辩论</option>
                <option value={3}>3 轮辩论</option>
                <option value={4}>4 轮辩论</option>
                <option value={5}>5 轮辩论</option>
              </select>
            )}
            {/* 开始按钮 */}
            {canStart && (
              <button
                onClick={handleStart}
                className="flex items-center gap-1.5 rounded-lg bg-purple-600 px-4 py-1.5 text-sm font-medium text-white transition hover:bg-purple-700"
              >
                <Play className="h-4 w-4" />
                开始庭审
              </button>
            )}
            {/* 停止按钮 */}
            {isRunning && (
              <button
                onClick={handleStop}
                className="flex items-center gap-1.5 rounded-lg bg-red-100 px-4 py-1.5 text-sm font-medium text-red-600 transition hover:bg-red-200"
              >
                <Square className="h-4 w-4 fill-current" />
                停止
              </button>
            )}
            {/* 导出按钮 */}
            {trialResult && !isRunning && (
              <button
                onClick={handleExport}
                className="flex items-center gap-1.5 rounded-lg bg-green-100 px-4 py-1.5 text-sm font-medium text-green-700 transition hover:bg-green-200"
              >
                <Download className="h-4 w-4" />
                导出记录
              </button>
            )}
            {/* 重置按钮 */}
            {hasStarted && !isRunning && (
              <button
                onClick={handleReset}
                className="flex items-center gap-1.5 rounded-lg bg-gray-100 px-4 py-1.5 text-sm font-medium text-gray-600 transition hover:bg-gray-200"
              >
                <RotateCcw className="h-4 w-4" />
                新庭审
              </button>
            )}
          </div>
        </div>
      </div>

      {/* 内容区 */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4">
        {/* 错误提示 */}
        {error && (
          <div className="mx-auto mb-4 flex max-w-4xl items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
            <AlertCircle className="h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        {/* 案件输入区 */}
        {!hasStarted && (
          <div className="mx-auto max-w-4xl">
            <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
              <label className="mb-2 block text-sm font-medium text-gray-700">
                案件描述
              </label>
              <textarea
                value={caseInput}
                onChange={(e) => setCaseInput(e.target.value)}
                placeholder="请输入案件详细描述，包括当事人、事实经过、争议焦点等。描述越详细，模拟效果越好。"
                rows={8}
                className="w-full resize-y rounded-lg border border-gray-300 bg-gray-50 px-4 py-3 text-sm text-gray-800 placeholder-gray-400 focus:border-purple-500 focus:bg-white focus:outline-none"
              />
              <div className="mt-2 flex items-center justify-between">
                <span className="text-xs text-gray-400">
                  {caseInput.trim().length < MIN_CASE_LENGTH
                    ? `至少输入 ${MIN_CASE_LENGTH} 字（当前 ${caseInput.trim().length} 字）`
                    : "可以开始庭审了"}
                </span>
                <span className="text-xs text-gray-400">
                  庭审流程：审判长开场 → 原告陈述 → 被告答辩 → 多轮辩论 → 法官判决
                </span>
              </div>

              {/* 示例案件 */}
              <div className="mt-6">
                <p className="mb-2 text-xs font-medium text-gray-500">或试试这些案例：</p>
                <div className="grid gap-2">
                  {EXAMPLES.map((ex, i) => (
                    <button
                      key={i}
                      onClick={() => setCaseInput(ex)}
                      className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-left text-xs text-gray-600 transition hover:border-purple-300 hover:bg-purple-50"
                    >
                      {ex}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 法庭布局 */}
        {hasStarted && (
          <div className="mx-auto max-w-6xl space-y-4">
            {/* 审判长席位（顶部中央） */}
            <CourtArea
              title="审判长"
              emoji="⚖️"
              areaClass="border-purple-200 bg-purple-50/60"
              headerClass="text-purple-800"
              speeches={chiefJudgeSpeeches}
            />

            {/* 原告席 | 被告席（中部两列） */}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <CourtArea
                title="原告席"
                emoji="📋"
                areaClass="border-blue-200 bg-blue-50/60"
                headerClass="text-blue-800"
                speeches={plaintiffSpeeches}
              />
              <CourtArea
                title="被告席"
                emoji="🛡️"
                areaClass="border-red-200 bg-red-50/60"
                headerClass="text-red-800"
                speeches={defendantSpeeches}
              />
            </div>

            {/* 法官席（底部） */}
            <CourtArea
              title="法官席"
              emoji="🔍"
              areaClass="border-green-200 bg-green-50/60"
              headerClass="text-green-800"
              speeches={judgeSpeeches.filter((s) => s.role === "judge")}
            />

            {/* 判决书 */}
            {trialResult?.verdict && !isRunning && (
              <VerdictPanel result={trialResult} />
            )}

            {/* 运行中提示 */}
            {isRunning && (
              <div className="flex items-center justify-center gap-2 py-4 text-sm text-gray-500">
                <Loader2 className="h-4 w-4 animate-spin" />
                庭审进行中...
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ========== 子组件：法庭区域 ==========

interface CourtAreaProps {
  title: string
  emoji: string
  areaClass: string
  headerClass: string
  speeches: SpeechCard[]
}

function CourtArea({
  title,
  emoji,
  areaClass,
  headerClass,
  speeches,
}: CourtAreaProps) {
  return (
    <div className={cn("rounded-xl border p-4", areaClass)}>
      <div className="mb-3 flex items-center gap-2">
        <span className="text-lg">{emoji}</span>
        <h2 className={cn("text-sm font-bold", headerClass)}>{title}</h2>
        {speeches.length > 0 && (
          <span className="ml-auto text-xs text-gray-400">
            {speeches.length} 条发言
          </span>
        )}
      </div>
      <div className="space-y-3">
        {speeches.length === 0 ? (
          <div className="py-4 text-center text-xs text-gray-400">
            等待发言...
          </div>
        ) : (
          speeches.map((speech) => (
            <SpeechBubble key={speech.id} speech={speech} />
          ))
        )}
      </div>
    </div>
  )
}

// ========== 子组件：发言气泡 ==========

interface SpeechBubbleProps {
  speech: SpeechCard
}

function SpeechBubble({ speech }: SpeechBubbleProps) {
  const info = ROLE_INFO[speech.role]
  const roundLabel = speech.round === 0
    ? "开场"
    : speech.role === "verdict"
      ? "最终判决"
      : `第 ${speech.round} 轮`

  return (
    <div className={cn("rounded-lg border bg-white p-3 shadow-sm", info.card)}>
      {/* 头部 */}
      <div className="mb-2 flex items-center justify-between">
        <span className={cn("rounded px-2 py-0.5 text-xs font-medium", info.badge)}>
          {info.emoji} {info.label}
        </span>
        <span className="text-xs text-gray-400">{roundLabel}</span>
      </div>
      {/* 内容 */}
      <div className="text-sm leading-relaxed text-gray-800">
        {speech.content ? (
          <>
            {speech.role === "verdict" ? (
              <MarkdownRenderer
                content={speech.content}
                className="prose prose-sm max-w-none"
              />
            ) : (
              <div className="whitespace-pre-wrap break-words">
                {speech.content}
              </div>
            )}
            {/* 流式光标 */}
            {!speech.isComplete && (
              <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-gray-400 align-middle" />
            )}
          </>
        ) : (
          // 等待内容时的加载动画
          <span className="inline-flex gap-1 text-gray-400">
            <span className="h-2 w-2 animate-bounce rounded-full bg-gray-300 [animation-delay:0ms]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-gray-300 [animation-delay:150ms]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-gray-300 [animation-delay:300ms]" />
          </span>
        )}
      </div>
    </div>
  )
}

// ========== 子组件：判决面板 ==========

interface VerdictPanelProps {
  result: TrialResult
}

function VerdictPanel({ result }: VerdictPanelProps) {
  const verdict = result.verdict
  if (!verdict) return null

  const winnerColor =
    verdict.winner === "原告"
      ? "bg-blue-100 text-blue-700 border-blue-300"
      : verdict.winner === "被告"
        ? "bg-red-100 text-red-700 border-red-300"
        : "bg-gray-100 text-gray-700 border-gray-300"

  return (
    <div className="rounded-xl border-2 border-amber-300 bg-amber-50/80 p-6 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        <Scale className="h-5 w-5 text-amber-600" />
        <h2 className="text-base font-bold text-amber-900">最终判决</h2>
      </div>

      {/* 胜诉方 */}
      <div className="mb-4 flex items-center gap-3">
        <span className="text-sm text-gray-600">判决结果：</span>
        <span className={cn("rounded-full border px-3 py-1 text-sm font-bold", winnerColor)}>
          {verdict.winner}
        </span>
      </div>

      {/* 胜率条 */}
      <div className="mb-4">
        <div className="mb-1 flex items-center justify-between text-xs text-gray-500">
          <span>原告 {verdict.plaintiff_win_rate.toFixed(0)}%</span>
          <span>被告 {verdict.defendant_win_rate.toFixed(0)}%</span>
        </div>
        <div className="flex h-3 overflow-hidden rounded-full bg-gray-200">
          <div
            className="bg-blue-500 transition-all duration-500"
            style={{ width: `${verdict.plaintiff_win_rate}%` }}
          />
          <div
            className="bg-red-500 transition-all duration-500"
            style={{ width: `${verdict.defendant_win_rate}%` }}
          />
        </div>
      </div>

      {/* 关键胜负点 */}
      {verdict.key_points.length > 0 && (
        <div className="mb-4">
          <h3 className="mb-2 text-sm font-semibold text-gray-700">关键胜负点</h3>
          <ul className="space-y-1">
            {verdict.key_points.map((point, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-600">
                <span className="mt-1 text-amber-500">•</span>
                {point}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 判决理由 */}
      {verdict.reasoning && (
        <div className="mb-4">
          <h3 className="mb-2 text-sm font-semibold text-gray-700">判决理由</h3>
          <div className="rounded-lg bg-white/60 p-3 text-sm text-gray-700">
            {verdict.reasoning}
          </div>
        </div>
      )}

      {/* 行动建议 */}
      {verdict.action_suggestions.length > 0 && (
        <div className="mb-4">
          <h3 className="mb-2 text-sm font-semibold text-gray-700">行动建议</h3>
          <ul className="space-y-1">
            {verdict.action_suggestions.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-600">
                <span className="mt-1 text-green-500">✓</span>
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 判决书全文 */}
      {verdict.full_text && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-gray-700">判决书全文</h3>
          <div className="rounded-lg bg-white/80 p-4">
            <MarkdownRenderer
              content={verdict.full_text}
              className="prose prose-sm max-w-none"
            />
          </div>
        </div>
      )}

      {/* 风险提示 */}
      <div className="mt-4 border-t border-amber-200 pt-3 text-xs text-gray-500">
        ⚠️ 以上分析仅基于 AI 模拟，不构成正式法律意见。复杂案件或正式诉讼前，建议咨询专业律师。
      </div>
    </div>
  )
}
