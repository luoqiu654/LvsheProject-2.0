import { useCallback, useEffect, useRef, useState } from "react"
import {
  Play,
  Square,
  RotateCcw,
  Download,
  AlertCircle,
  Loader2,
  Scale,
  Gavel,
  MessageCircleQuestion,
  Send,
  Wrench,
  ChevronDown,
} from "lucide-react"
import {
  streamTrial,
  submitAnswer,
  type TrialResult,
  type TrialRole,
  type SpeechKind,
  type UserQuestion,
  type TrialVerdict,
  type EvidenceItem,
  type ToolCallRecord,
} from "@/api/expert"
import { MarkdownRenderer } from "@/components/shared/MarkdownRenderer"
import { ThinkingPanel } from "@/components/shared/ThinkingPanel"
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

// ========== 发言种类标签 ==========

const KIND_LABEL: Record<SpeechKind, string> = {
  opening: "开场白",
  statement: "陈述",
  inquiry: "法官追问",
  answer: "回答法官",
  verdict: "判决书",
  user: "用户补充",
}

// ========== 发言卡片类型 ==========

interface SpeechCard {
  id: string
  role: TrialRole
  round: number
  content: string
  isComplete: boolean
  kind: SpeechKind
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
  const [verdict, setVerdict] = useState<TrialVerdict | null>(null)
  const [error, setError] = useState<string | null>(null)
  // 交互式庭审状态
  const [trialId, setTrialId] = useState<string | null>(null)
  const [pendingQuestion, setPendingQuestion] = useState<UserQuestion | null>(
    null,
  )
  const [answerInput, setAnswerInput] = useState("")
  const [submittingAnswer, setSubmittingAnswer] = useState(false)
  // 思考过程（按角色累积 reasoning_content 文本）
  const [thinkingContent, setThinkingContent] = useState<
    Record<string, string>
  >({})
  // 编排步骤（按角色累积 thinking_note，离散步骤数组）
  const [thinkingStepsByRole, setThinkingStepsByRole] = useState<
    Record<string, string[]>
  >({})
  // 法官证据梳理清单
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([])
  // Agent 工具调用记录（按角色累积 tool_call/tool_result 事件，展示自主 Agent plan→tool→final）
  const [toolCallsByRole, setToolCallsByRole] = useState<
    Record<string, ToolCallRecord[]>
  >({})
  // 判决打回提示（法官被打回重判时显示，保持 loading 态直到最终 verdict）
  const [verdictRebuttalMsg, setVerdictRebuttalMsg] = useState<string | null>(
    null,
  )
  const [currentlyThinking, setCurrentlyThinking] = useState<TrialRole | null>(
    null,
  )
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

  // 查找当前角色+轮次+种类的未完成发言卡片（用于追加流式文本）
  const findCurrentSpeech = useCallback(
    (
      list: SpeechCard[],
      role: TrialRole,
      round: number,
      kind: SpeechKind,
    ): SpeechCard | undefined => {
      // 从末尾向前查找：最后一个匹配且未完成的卡片
      for (let i = list.length - 1; i >= 0; i--) {
        const s = list[i]
        if (
          s.role === role &&
          s.round === round &&
          s.kind === kind &&
          !s.isComplete
        ) {
          return s
        }
      }
      return undefined
    },
    [],
  )

  // 开始庭审
  const handleStart = useCallback(async () => {
    const text = caseInput.trim()
    if (text.length < MIN_CASE_LENGTH || isRunning) return

    setSpeeches([])
    setTrialResult(null)
    setVerdict(null)
    setError(null)
    setIsRunning(true)
    setTrialId(null)
    setPendingQuestion(null)
    setAnswerInput("")
    setThinkingContent({})
    setThinkingStepsByRole({})
    setEvidenceList([])
    setVerdictRebuttalMsg(null)
    setCurrentlyThinking(null)
    setToolCallsByRole({})

    const controller = new AbortController()
    abortRef.current = controller

    await streamTrial(
      { case_description: text, rounds },
      {
        signal: controller.signal,
        onTrialStarted: (id) => setTrialId(id),
        onThinking: (role, thinkText, _round) => {
          setCurrentlyThinking(role)
          setThinkingContent((prev) => ({
            ...prev,
            [role]: (prev[role] || "") + thinkText,
          }))
        },
        onThinkingNote: (role, step, _round) => {
          setThinkingStepsByRole((prev) => ({
            ...prev,
            [role]: [...(prev[role] || []), step],
          }))
          // 判决打回检测：法官被打回重判时，保持 loading 态并显示提示
          if (
            role === "judge" &&
            (step.includes("打回重审") || step.includes("重新撰写"))
          ) {
            setVerdictRebuttalMsg(step)
            setCurrentlyThinking("judge")
          }
        },
        onSpeech: (role, speechText, kind, round) => {
          // 角色开始发言，思考阶段结束（不清空已积累的思考内容）
          setCurrentlyThinking((prev) => (prev === role ? null : prev))
          setSpeeches((prev) => {
            const existing = findCurrentSpeech(prev, role, round, kind)
            if (existing) {
              // 追加到现有卡片
              return prev.map((s) =>
                s.id === existing.id
                  ? { ...s, content: s.content + speechText }
                  : s,
              )
            }
            // 创建新卡片
            return [
              ...prev,
              {
                id: crypto.randomUUID(),
                role,
                round,
                content: speechText,
                isComplete: false,
                kind,
              },
            ]
          })
        },
        onSpeechEnd: (role, kind, round) => {
          setSpeeches((prev) => {
            const existing = findCurrentSpeech(prev, role, round, kind)
            if (existing) {
              return prev.map((s) =>
                s.id === existing.id ? { ...s, isComplete: true } : s,
              )
            }
            return prev
          })
        },
        onToolCall: (role, tool, input, round) => {
          setToolCallsByRole((prev) => {
            const list = prev[role] ? [...prev[role]!] : []
            list.push({ role, tool, input, round, output: undefined })
            return { ...prev, [role]: list }
          })
        },
        onToolResult: (role, tool, output, _round) => {
          setToolCallsByRole((prev) => {
            const oldList = prev[role] || []
            const newList = [...oldList]
            for (let i = newList.length - 1; i >= 0; i--) {
              if (newList[i].tool === tool && newList[i].output === undefined) {
                newList[i] = { ...newList[i], output }
                break
              }
            }
            return { ...prev, [role]: newList }
          })
        },
        onUserQuestion: (q) => {
          setPendingQuestion(q)
          setAnswerInput("")
        },
        onUserAnswer: (_questionId, answer, round) => {
          // 用户回答作为审判长席位的"用户补充"卡片显示
          setSpeeches((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: "chief_judge" as TrialRole,
              round,
              content: answer,
              isComplete: true,
              kind: "user" as SpeechKind,
            },
          ])
        },
        onRoundEnd: () => {
          setCurrentlyThinking(null)
        },
        onVerdict: (v, _round) => {
          setVerdict(v)
          setCurrentlyThinking(null)
          // 新判决到达，清除打回提示（若此判决仍被打回，下一条 thinking_note 会重新设置）
          setVerdictRebuttalMsg(null)
        },
        onEvidenceList: (items, _round) => {
          setEvidenceList(items)
        },
        onDone: (result) => {
          setCurrentlyThinking(null)
          setVerdictRebuttalMsg(null)
          // SSE 流结束（含中断）时清理模态窗状态，避免卡死
          setPendingQuestion(null)
          setSubmittingAnswer(false)
          if (result) {
            setTrialResult(result)
            if (result.verdict) {
              setVerdict(result.verdict)
            }
          }
        },
        onError: (err) => {
          setCurrentlyThinking(null)
          setVerdictRebuttalMsg(null)
          // SSE 流出错时清理模态窗状态，避免卡死
          setPendingQuestion(null)
          setSubmittingAnswer(false)
          setError(err)
        },
      },
    )

    setIsRunning(false)
    abortRef.current = null
  }, [caseInput, isRunning, rounds, findCurrentSpeech])

  // 提交用户对法官追问的回答（含重试 + 失败强制关闭模态窗，避免卡死）
  const handleSubmitAnswer = useCallback(async () => {
    if (!trialId || !pendingQuestion) return
    const answer = answerInput.trim()
    if (!answer) return
    setSubmittingAnswer(true)
    try {
      // 重试 3 次，每次间隔 500ms（容忍后端 status 竞态切换）
      let lastErr: unknown = null
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          await submitAnswer(trialId, pendingQuestion.question_id, answer)
          setPendingQuestion(null)
          setAnswerInput("")
          return
        } catch (e) {
          lastErr = e
          if (attempt < 2) await new Promise((r) => setTimeout(r, 500))
        }
      }
      throw lastErr
    } catch (e) {
      setError(e instanceof Error ? e.message : "提交回答失败")
      // 关键：失败后仍关闭模态窗，避免永久卡死（用户可重新启动庭审）
      setPendingQuestion(null)
      setAnswerInput("")
    } finally {
      setSubmittingAnswer(false)
    }
  }, [trialId, pendingQuestion, answerInput])

  // 停止庭审
  const handleStop = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setIsRunning(false)
    setCurrentlyThinking(null)
    setVerdictRebuttalMsg(null)
    // 标记当前未完成的发言为已完成
    setSpeeches((prev) => prev.map((s) => ({ ...s, isComplete: true })))
  }, [])

  // 重置
  const handleReset = useCallback(() => {
    if (isRunning) handleStop()
    setSpeeches([])
    setTrialResult(null)
    setVerdict(null)
    setError(null)
    setCaseInput("")
    setTrialId(null)
    setPendingQuestion(null)
    setAnswerInput("")
    setThinkingContent({})
    setThinkingStepsByRole({})
    setEvidenceList([])
    setVerdictRebuttalMsg(null)
    setCurrentlyThinking(null)
    setToolCallsByRole({})
  }, [isRunning, handleStop])

  // 导出庭审记录
  const handleExport = useCallback(() => {
    const result = trialResult
    const v = verdict
    if (!result && !v) return

    const lines: string[] = []
    lines.push("# 法庭模拟庭审记录")
    lines.push("")
    if (result) {
      lines.push(`**庭审ID**: ${result.trial_id}`)
      lines.push(`**创建时间**: ${result.created_at}`)
      lines.push(`**案件**: ${result.case}`)
      lines.push("")
      lines.push("---")
      lines.push("")

      // 过滤掉判决类发言（判决在末尾单独导出）
      const nonVerdictSpeeches = result.speeches.filter(
        (s) => s.kind !== "verdict",
      )

      // 审判长开场白（从 speeches 中筛 kind==="opening"）
      const openingSpeeches = nonVerdictSpeeches.filter(
        (s) => s.kind === "opening",
      )
      if (openingSpeeches.length > 0) {
        lines.push("## 审判长开场白")
        lines.push("")
        for (const s of openingSpeeches) {
          lines.push(s.text)
          lines.push("")
        }
      }

      // 按轮次分组输出辩论发言（rounds 是轮数计数）
      const totalRounds = result.rounds
      for (let n = 1; n <= totalRounds; n++) {
        const roundSpeeches = nonVerdictSpeeches.filter(
          (s) => s.round === n && s.kind !== "opening",
        )
        if (roundSpeeches.length === 0) continue
        lines.push("---")
        lines.push("")
        lines.push(`## 第 ${n} 轮辩论`)
        lines.push("")
        for (const sp of roundSpeeches) {
          const roleLabel = ROLE_INFO[sp.role]?.label ?? sp.role
          const kindLabel = KIND_LABEL[sp.kind as SpeechKind]
          lines.push(
            `### ${roleLabel}${kindLabel && kindLabel !== "陈述" ? ` · ${kindLabel}` : ""}`,
          )
          lines.push("")
          lines.push(sp.text)
          lines.push("")
        }
      }
    }

    if (v) {
      lines.push("---")
      lines.push("")
      lines.push("## 最终判决")
      lines.push("")
      lines.push(`**胜诉方**: ${v.winner}`)
      lines.push("")
      if (v.compensation) {
        lines.push("### 赔偿 / 责任承担")
        lines.push(v.compensation)
        lines.push("")
      }
      lines.push("### 判决理由")
      lines.push(v.reasoning)
      lines.push("")
      lines.push("### 判决书全文")
      lines.push("")
      lines.push(v.full_text)
    }

    const md = lines.join("\n")
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `庭审记录_${result?.trial_id ?? "trial"}.md`
    a.click()
    URL.revokeObjectURL(url)
  }, [trialResult, verdict])

  // 按角色分组发言
  const chiefJudgeSpeeches = speeches.filter((s) => s.role === "chief_judge")
  const plaintiffSpeeches = speeches.filter((s) => s.role === "plaintiff")
  const defendantSpeeches = speeches.filter((s) => s.role === "defendant")
  const judgeSpeeches = speeches.filter(
    (s) => s.role === "judge" || s.role === "verdict",
  )

  const hasStarted = speeches.length > 0 || isRunning
  const canStart =
    caseInput.trim().length >= MIN_CASE_LENGTH && !isRunning

  return (
    <div className="flex h-full flex-col overflow-hidden bg-gray-50">
      {/* 顶部标题栏 */}
      <div className="shrink-0 border-b border-gray-200 bg-white px-6 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Gavel className="h-5 w-5 text-purple-600" />
            <h1 className="text-lg font-bold text-gray-900">
              专家会诊 · 法庭模拟
            </h1>
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
            {(verdict || trialResult) && !isRunning && (
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
                <p className="mb-2 text-xs font-medium text-gray-500">
                  或试试这些案例：
                </p>
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
              thinkingContent={thinkingContent["chief_judge"] || ""}
              thinkingSteps={thinkingStepsByRole["chief_judge"] || []}
              isThinking={currentlyThinking === "chief_judge"}
            />

            {/* 原告席 | 被告席（中部两列） */}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <CourtArea
                title="原告席"
                emoji="📋"
                areaClass="border-blue-200 bg-blue-50/60"
                headerClass="text-blue-800"
                speeches={plaintiffSpeeches}
                thinkingContent={thinkingContent["plaintiff"] || ""}
                thinkingSteps={thinkingStepsByRole["plaintiff"] || []}
                isThinking={currentlyThinking === "plaintiff"}
              />
              <CourtArea
                title="被告席"
                emoji="🛡️"
                areaClass="border-red-200 bg-red-50/60"
                headerClass="text-red-800"
                speeches={defendantSpeeches}
                thinkingContent={thinkingContent["defendant"] || ""}
                thinkingSteps={thinkingStepsByRole["defendant"] || []}
                isThinking={currentlyThinking === "defendant"}
              />
            </div>

            {/* 法官证据梳理清单 */}
            {evidenceList.length > 0 && (
              <div className="rounded-xl border-2 border-amber-200 bg-amber-50/60 p-4">
                <div className="mb-2 flex items-center gap-2">
                  <Scale className="h-4 w-4 text-amber-600" />
                  <h3 className="text-sm font-bold text-amber-900">
                    法官证据梳理
                  </h3>
                </div>
                <ul className="space-y-1.5">
                  {evidenceList.map((ev, i) => (
                    <li
                      key={i}
                      className="rounded-lg border border-amber-100 bg-white/70 px-3 py-2"
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium text-amber-700">
                          证据 {i + 1}
                        </span>
                        <span className="text-sm font-medium text-gray-800">
                          {ev.name}
                        </span>
                        <span className="ml-auto text-xs text-gray-400">
                          {ev.target_party === "plaintiff"
                            ? "向原告确认"
                            : ev.target_party === "defendant"
                              ? "向被告确认"
                              : "向您确认"}
                        </span>
                      </div>
                      {ev.why_key && (
                        <p className="mt-1 text-xs text-gray-600">
                          {ev.why_key}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Agent 工具调用折叠面板（自主 Agent plan→tool→final 模式展示） */}
            <ToolCallPanel
              toolCallsByRole={toolCallsByRole}
              planStepsByRole={thinkingStepsByRole}
            />

            {/* 法官席（底部） */}
            <CourtArea
              title="法官席"
              emoji="🔍"
              areaClass="border-green-200 bg-green-50/60"
              headerClass="text-green-800"
              speeches={judgeSpeeches.filter((s) => s.role === "judge")}
              thinkingContent={thinkingContent["judge"] || ""}
              thinkingSteps={thinkingStepsByRole["judge"] || []}
              isThinking={currentlyThinking === "judge"}
            />

            {/* 判决书 */}
            {verdict && !isRunning && <VerdictPanel verdict={verdict} />}

            {/* 运行中提示 */}
            {isRunning && !pendingQuestion && (
              <div className="flex items-center justify-center gap-2 py-4 text-sm text-gray-500">
                <Loader2 className="h-4 w-4 animate-spin" />
                {verdictRebuttalMsg ?? "庭审进行中..."}
              </div>
            )}

            {/* 等待用户回答提示 */}
            {isRunning && pendingQuestion && (
              <div className="flex items-center justify-center gap-2 py-4 text-sm text-amber-600">
                <MessageCircleQuestion className="h-4 w-4" />
                等待您回答法官的追问...
              </div>
            )}
          </div>
        )}

        {/* 用户回答法官追问的模态窗口 */}
        {pendingQuestion && (
          <UserQuestionModal
            question={pendingQuestion}
            answer={answerInput}
            onAnswerChange={setAnswerInput}
            onSubmit={handleSubmitAnswer}
            submitting={submittingAnswer}
          />
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
  thinkingContent: string
  thinkingSteps: string[]
  isThinking: boolean
}

function CourtArea({
  title,
  emoji,
  areaClass,
  headerClass,
  speeches,
  thinkingContent,
  thinkingSteps,
  isThinking,
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
      {/* 思考过程折叠面板（steps 展示编排提示 + content 展示 reasoning_content） */}
      {(thinkingSteps.length > 0 || thinkingContent || isThinking) && (
        <ThinkingPanel
          steps={thinkingSteps.length > 0 ? thinkingSteps : undefined}
          content={thinkingContent || undefined}
          isThinking={isThinking}
          className="mb-3"
        />
      )}
      <div className="space-y-3">
        {speeches.length === 0 && !isThinking ? (
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

// ========== 子组件：Agent 工具调用折叠面板 ==========

interface ToolCallPanelProps {
  toolCallsByRole: Record<string, ToolCallRecord[]>
  /** 自主 Agent 的 plan 步骤（用 thinking_note 近似展示） */
  planStepsByRole: Record<string, string[]>
}

function ToolCallPanel({
  toolCallsByRole,
  planStepsByRole,
}: ToolCallPanelProps) {
  const [expanded, setExpanded] = useState(true)
  // 角色出场顺序
  const roleOrder: TrialRole[] = [
    "chief_judge",
    "plaintiff",
    "defendant",
    "judge",
  ]
  const roles = roleOrder.filter(
    (r) =>
      (toolCallsByRole[r]?.length ?? 0) > 0 ||
      (planStepsByRole[r]?.length ?? 0) > 0,
  )
  const totalTools = roles.reduce(
    (sum, r) => sum + (toolCallsByRole[r]?.length ?? 0),
    0,
  )
  if (totalTools === 0 && roles.length === 0) return null

  return (
    <div className="rounded-xl border border-teal-200 bg-teal-50/40">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm font-medium text-teal-800 transition hover:bg-teal-100/40"
      >
        <Wrench className="h-4 w-4 text-teal-600" />
        <span className="flex-1">Agent 工具调用</span>
        {totalTools > 0 && (
          <span className="text-xs text-teal-500">{totalTools} 次调用</span>
        )}
        <ChevronDown
          className={cn(
            "h-4 w-4 transition-transform",
            expanded && "rotate-180",
          )}
        />
      </button>
      {expanded && (
        <div className="space-y-3 border-t border-teal-100 px-4 py-3">
          {roles.map((role) => {
            const info = ROLE_INFO[role]
            const calls = toolCallsByRole[role] || []
            const steps = planStepsByRole[role] || []
            return (
              <div
                key={role}
                className="rounded-lg border border-teal-100 bg-white/60 p-3"
              >
                <div className="mb-2 flex items-center gap-2">
                  <span
                    className={cn(
                      "rounded px-2 py-0.5 text-xs font-medium",
                      info.badge,
                    )}
                  >
                    {info.emoji} {info.label}
                  </span>
                </div>
                {/* plan 步骤（自主 Agent 的 plan 阶段，用 thinking_note 近似展示） */}
                {steps.length > 0 && (
                  <div className="mb-2">
                    <p className="mb-1 text-[11px] font-medium text-teal-600">
                      规划
                    </p>
                    <p className="whitespace-pre-wrap break-words text-xs leading-relaxed text-gray-600">
                      {steps.join(" ")}
                    </p>
                  </div>
                )}
                {/* 工具调用记录（tool 阶段） */}
                {calls.length > 0 ? (
                  <div className="space-y-2">
                    <p className="text-[11px] font-medium text-teal-600">
                      工具调用
                    </p>
                    {calls.map((c, i) => (
                      <div
                        key={i}
                        className="rounded-md border border-teal-100 bg-teal-50/40 px-3 py-2 text-xs"
                      >
                        <div className="mb-1 flex items-center gap-2">
                          <span className="rounded bg-teal-100 px-1.5 py-0.5 font-mono text-[11px] text-teal-700">
                            {c.tool}
                          </span>
                          <span className="text-gray-400">
                            第 {c.round} 轮
                          </span>
                          {c.output === undefined && (
                            <Loader2 className="h-3 w-3 animate-spin text-teal-400" />
                          )}
                        </div>
                        {c.input && (
                          <div className="mb-1">
                            <span className="text-gray-400">输入：</span>
                            <span className="whitespace-pre-wrap break-words text-gray-600">
                              {c.input}
                            </span>
                          </div>
                        )}
                        {c.output !== undefined && c.output && (
                          <div>
                            <span className="text-gray-400">结果：</span>
                            <span className="whitespace-pre-wrap break-words text-gray-600">
                              {c.output}
                            </span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-gray-400">暂无工具调用</p>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ========== 子组件：发言气泡 ==========

interface SpeechBubbleProps {
  speech: SpeechCard
}

function SpeechBubble({ speech }: SpeechBubbleProps) {
  const info = ROLE_INFO[speech.role]
  const kindLabel = KIND_LABEL[speech.kind] || ""
  const roundLabel =
    speech.round === 0
      ? "开场"
      : speech.role === "verdict"
        ? "最终判决"
        : `第 ${speech.round} 轮`

  // 用户补充证据的特殊样式
  const isUserAnswer = speech.kind === "user"

  return (
    <div className={cn("rounded-lg border bg-white p-3 shadow-sm", info.card)}>
      {/* 头部 */}
      <div className="mb-2 flex items-center justify-between">
        <span
          className={cn(
            "rounded px-2 py-0.5 text-xs font-medium",
            info.badge,
          )}
        >
          {info.emoji} {info.label}
          {kindLabel && kindLabel !== "陈述" && (
            <span className="ml-1 opacity-70">· {kindLabel}</span>
          )}
        </span>
        <span className="text-xs text-gray-400">{roundLabel}</span>
      </div>
      {/* 内容 */}
      <div className="text-sm leading-relaxed text-gray-800">
        {isUserAnswer ? (
          // 用户回答用特殊样式突出
          <div className="rounded-md border border-amber-200 bg-amber-50/70 px-3 py-2">
            <span className="mb-1 block text-xs font-medium text-amber-700">
              您的回答：
            </span>
            <div className="whitespace-pre-wrap break-words">
              {speech.content}
            </div>
          </div>
        ) : speech.content ? (
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
  verdict: TrialVerdict
}

function VerdictPanel({ verdict }: VerdictPanelProps) {
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
        <span
          className={cn(
            "rounded-full border px-3 py-1 text-sm font-bold",
            winnerColor,
          )}
        >
          {verdict.winner}
        </span>
      </div>

      {/* 赔偿/责任承担说明 */}
      {verdict.compensation && (
        <div className="mb-4">
          <h3 className="mb-2 text-sm font-semibold text-gray-700">
            赔偿 / 责任承担
          </h3>
          <div className="rounded-lg bg-white/60 p-3 text-sm text-gray-700">
            {verdict.compensation}
          </div>
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

      {/* 判决书全文 */}
      {verdict.full_text && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-gray-700">
            判决书全文
          </h3>
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

// ========== 子组件：用户回答法官追问的模态窗 ==========

interface UserQuestionModalProps {
  question: UserQuestion
  answer: string
  onAnswerChange: (v: string) => void
  onSubmit: () => void
  submitting: boolean
}

function UserQuestionModal({
  question,
  answer,
  onAnswerChange,
  onSubmit,
  submitting,
}: UserQuestionModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-2xl border-2 border-amber-300 bg-white p-6 shadow-2xl">
        {/* 头部 */}
        <div className="mb-4 flex items-center gap-2">
          <MessageCircleQuestion className="h-5 w-5 text-amber-600" />
          <h3 className="text-base font-bold text-amber-900">
            法官需要您确认证据
          </h3>
        </div>

        {/* 证据名称（如有） */}
        {question.evidence_name && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-100/60 px-3 py-2">
            <span className="text-xs font-medium text-amber-700">
              证据项：
            </span>
            <span className="text-sm font-bold text-amber-900">
              {question.evidence_name}
            </span>
          </div>
        )}

        {/* 问题 */}
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50/70 p-3">
          <p className="mb-1 text-xs font-medium text-amber-700">
            法官的问题
          </p>
          <p className="text-sm leading-relaxed text-gray-800">
            {question.question}
          </p>
        </div>

        {/* 上下文 */}
        {question.context && (
          <div className="mb-4 rounded-lg bg-gray-50 p-3">
            <p className="mb-1 text-xs font-medium text-gray-500">
              为什么问这个问题
            </p>
            <p className="text-xs leading-relaxed text-gray-600">
              {question.context}
            </p>
          </div>
        )}

        {/* 回答输入 */}
        <div className="mb-4">
          <label className="mb-1.5 block text-xs font-medium text-gray-600">
            您的回答
          </label>
          <textarea
            value={answer}
            onChange={(e) => onAnswerChange(e.target.value)}
            placeholder="请回答是/否，或详细说明您持有的证据情况..."
            rows={3}
            autoFocus
            className="w-full resize-y rounded-lg border border-gray-300 bg-gray-50 px-3 py-2 text-sm text-gray-800 placeholder-gray-400 focus:border-amber-500 focus:bg-white focus:outline-none"
            onKeyDown={(e) => {
              if (
                e.key === "Enter" &&
                (e.ctrlKey || e.metaKey) &&
                !submitting
              ) {
                onSubmit()
              }
            }}
          />
          <p className="mt-1 text-xs text-gray-400">
            提示：Ctrl/⌘ + Enter 快速提交
          </p>
        </div>

        {/* 快捷回答按钮 */}
        <div className="mb-4 flex gap-2">
          {["是", "否", "我需要补充说明"].map((preset) => (
            <button
              key={preset}
              type="button"
              onClick={() => onAnswerChange(preset)}
              className="rounded-md border border-gray-200 bg-gray-50 px-3 py-1 text-xs text-gray-600 transition hover:border-amber-300 hover:bg-amber-50"
            >
              {preset}
            </button>
          ))}
        </div>

        {/* 提交按钮 */}
        <button
          type="button"
          onClick={onSubmit}
          disabled={!answer.trim() || submitting}
          className={cn(
            "flex w-full items-center justify-center gap-1.5 rounded-lg px-4 py-2.5 text-sm font-medium text-white transition",
            !answer.trim() || submitting
              ? "cursor-not-allowed bg-gray-300"
              : "bg-amber-600 hover:bg-amber-700",
          )}
        >
          {submitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              提交中...
            </>
          ) : (
            <>
              <Send className="h-4 w-4" />
              提交回答
            </>
          )}
        </button>
      </div>
    </div>
  )
}
