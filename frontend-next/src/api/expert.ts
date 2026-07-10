import client from "./client"

// ========== 类型定义 ==========

/** 庭审角色 */
export type TrialRole =
  | "chief_judge"   // 审判长
  | "plaintiff"     // 原告
  | "defendant"     // 被告
  | "judge"         // 中立法官（追问/决策）
  | "verdict"       // 判决

/** 单条发言记录（done 事件 result.speeches 项，与后端 _build_result 一致） */
export interface TrialSpeech {
  role: TrialRole
  kind: string
  text: string
  round: number
}

/** 用户回答记录（done 事件 result.user_answers 项） */
export interface TrialUserAnswer {
  question_id: string
  question: string
  answer: string
  content: string
  round: number
}

/** 法官判决（结构化，与后端 court_orchestrator._verdict_to_dict 一致） */
export interface TrialVerdict {
  winner: string                       // "原告胜诉" / "被告胜诉" / "部分支持" / "无法判断"
  reasoning: string                    // 判决理由（非"LLM 服务不可用"误导文案）
  full_text: string                    // 完整判决书文本
  compensation: string                 // 赔偿/责任承担说明（可能为空）
}

/** 庭审完整结果（done 事件的 result，与后端 court_orchestrator._build_result 一致） */
export interface TrialResult {
  trial_id: string
  case: string
  rounds: number                       // 辩论轮数
  speeches: TrialSpeech[]
  evidence_items: EvidenceItem[]
  user_answers: TrialUserAnswer[]
  user_said_unknown: boolean
  verdict: TrialVerdict | null
  retry_count: number                  // 判决打回重试次数
  created_at: string
}

/** 发言种类（区分陈述 / 追问 / 回答 / 开场 / 判决 / 用户） */
export type SpeechKind =
  | "opening"     // 审判长开场
  | "statement"   // 原被告陈述
  | "inquiry"     // 法官追问
  | "answer"      // 原被告回答法官
  | "verdict"     // 判决
  | "user"        // 用户回答

/** 用户问题（法官触发的证据询问，需用户补充信息） */
export interface UserQuestion {
  question_id: string
  question: string
  context: string
  round: number
  /** 对应的证据项名称（证据梳理阶段追问时携带） */
  evidence_name?: string
}

/** 证据项（法官梳理的关键证据清单） */
export interface EvidenceItem {
  name: string
  why_key: string
  target_party: "plaintiff" | "defendant" | "user"
}

/** SSE 流式事件类型（与后端 multi_agents.py 的 "type" 字段一致） */
export type TrialEventType =
  | "trial_started"
  | "thinking"
  | "thinking_note"     // 编排提示（离散步骤，如"法官正在审查..."）
  | "speech"
  | "speech_end"
  | "tool_call"         // 自主 Agent 工具调用记录
  | "tool_result"       // 工具调用结果
  | "user_question"
  | "user_answer"
  | "round_end"
  | "verdict"
  | "evidence_list"     // 法官证据梳理清单
  | "done"
  | "error"

/** 工具调用记录项（自主 Agent plan→tool→final 模式中的 tool 步骤） */
export interface ToolCallRecord {
  /** 调用方角色 */
  role: TrialRole
  /** 工具名称，如 "law_search" */
  tool: string
  /** 工具输入 */
  input?: string
  /** 工具输出（tool_result 事件携带） */
  output?: string
  /** 轮次 */
  round: number
}

/** SSE 流式事件（data: {JSON} 的 JSON 结构） */
export interface TrialStreamEvent {
  type: TrialEventType
  // 通用字段
  role?: TrialRole
  text?: string
  round?: number
  // speech / speech_end
  kind?: SpeechKind
  // trial_started / done
  trial_id?: string
  // thinking
  // speech
  // user_question
  question_id?: string
  question?: string
  context?: string
  // user_answer
  answer?: string
  // verdict
  verdict?: TrialVerdict
  // done
  result?: TrialResult
  // error
  message?: string
  // evidence_list
  items?: EvidenceItem[]
  // user_question (evidence_name 附加字段)
  evidence_name?: string
  // tool_call / tool_result（自主 Agent 工具调用）
  tool?: string
  input?: string
  output?: string
}

/** 庭审请求参数 */
export interface TrialParams {
  case_description: string
  rounds?: number
}

/** streamTrial 的回调集合 */
export interface TrialStreamCallbacks {
  signal?: AbortSignal
  /** 庭审已启动，拿到 trial_id */
  onTrialStarted?: (trialId: string) => void
  /** 思考过程片段（reasoning_content 流式 / 一次性通知） */
  onThinking?: (role: TrialRole, text: string, round: number) => void
  /** 编排提示（离散步骤，如"法官正在审查..."），与 reasoning 分离 */
  onThinkingNote?: (role: TrialRole, step: string, round: number) => void
  /** 发言片段（增量文本，前端需累加到当前发言） */
  onSpeech?: (role: TrialRole, text: string, kind: SpeechKind, round: number) => void
  /** 某角色的某段发言结束（标记当前发言卡片为完成） */
  onSpeechEnd?: (role: TrialRole, kind: SpeechKind, round: number) => void
  /** 自主 Agent 工具调用（plan→tool→final 中的 tool 步骤） */
  onToolCall?: (role: TrialRole, tool: string, input: string, round: number) => void
  /** 工具调用结果 */
  onToolResult?: (role: TrialRole, tool: string, output: string, round: number) => void
  /** 法官需要用户补充证据，流暂停，前端弹模态窗 */
  onUserQuestion?: (question: UserQuestion) => void
  /** 用户回答已收到并回传（前端可展示用户回答卡片） */
  onUserAnswer?: (questionId: string, answer: string, round: number) => void
  /** 一轮辩论结束 */
  onRoundEnd?: (round: number) => void
  /** 最终判决（结构化） */
  onVerdict?: (verdict: TrialVerdict, round: number) => void
  /** 法官证据梳理清单（主动梳理） */
  onEvidenceList?: (items: EvidenceItem[], round: number) => void
  /** 庭审完成，result 为完整结果（可能含 verdict） */
  onDone?: (result: TrialResult | undefined) => void
  /** 出错 */
  onError?: (err: string) => void
}

// ========== API 函数 ==========

/**
 * 启动庭审（非流式）。
 *
 * 返回完整的 TrialResult。庭审可能耗时较长（每轮多次 LLM 调用 + 判决），
 * 已设置 5 分钟超时。如需实时显示建议使用 streamTrial。
 */
export async function startTrial(
  params: TrialParams,
): Promise<TrialResult> {
  const res = await client.post<TrialResult>(
    "/api/expert/trial",
    {
      case_description: params.case_description,
      rounds: params.rounds ?? 2,
    },
    { timeout: 300_000 },
  )
  return res.data
}

/**
 * 启动庭审（SSE 流式交互）。
 *
 * 后端事件格式（data: {JSON}\n\n）：
 *   {"type":"trial_started","trial_id":"..."}
 *   {"type":"thinking","role":"plaintiff","text":"...","round":1}
 *   {"type":"speech","role":"plaintiff","text":"...","kind":"statement","round":1}
 *   {"type":"speech_end","role":"plaintiff","kind":"statement","round":1}
 *   {"type":"user_question","question_id":"q1_p","question":"...","context":"...","round":1}
 *   （流暂停，等待用户回答）
 *   {"type":"user_answer","question_id":"q1_p","answer":"...","round":1}
 *   {"type":"round_end","round":1}
 *   {"type":"verdict","verdict":{...},"round":N}
 *   {"type":"done","trial_id":"...","result":{...}}
 *   {"type":"error","message":"..."}
 *
 * 当收到 user_question 事件时，流暂停，调用 onUserQuestion 让前端弹模态窗，
 * 前端收集用户回答后调用 submitAnswer 提交，庭审继续。
 */
export async function streamTrial(
  params: TrialParams,
  opts: TrialStreamCallbacks,
): Promise<void> {
  const body = {
    case_description: params.case_description,
    rounds: params.rounds ?? 2,
  }

  let response: Response
  try {
    response = await fetch("/api/expert/trial/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: opts.signal,
    })
  } catch (e: unknown) {
    if (e instanceof Error && e.name === "AbortError") return
    opts.onError?.(e instanceof Error ? e.message : "网络请求失败")
    return
  }

  if (!response.ok || !response.body) {
    opts.onError?.(`HTTP ${response.status}`)
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // 解析 SSE 事件（以 data: 开头，\n\n 分隔）
      const parts = buffer.split("\n\n")
      buffer = parts.pop() || ""

      for (const part of parts) {
        const line = part.trim()
        if (!line.startsWith("data:")) continue
        const payload = line.slice(5).trim()
        if (!payload) continue
        if (payload === "[DONE]") {
          opts.onDone?.(undefined)
          return
        }
        try {
          const event: TrialStreamEvent = JSON.parse(payload)
          dispatchEvent(event, opts)
          if (event.type === "done" || event.type === "error") return
        } catch {
          // 忽略无法解析的行
        }
      }
    }
    opts.onDone?.(undefined)
  } catch (e: unknown) {
    if (e instanceof Error && e.name === "AbortError") return
    opts.onError?.(e instanceof Error ? e.message : "流式读取失败")
  }
}

/** 将单个 SSE 事件分发到对应回调 */
function dispatchEvent(
  event: TrialStreamEvent,
  opts: TrialStreamCallbacks,
): void {
  switch (event.type) {
    case "trial_started":
      if (event.trial_id) opts.onTrialStarted?.(event.trial_id)
      break
    case "thinking":
      if (event.role && event.text) {
        opts.onThinking?.(
          event.role,
          event.text,
          event.round ?? 0,
        )
      }
      break
    case "thinking_note":
      if (event.role && event.text) {
        opts.onThinkingNote?.(
          event.role,
          event.text,
          event.round ?? 0,
        )
      }
      break
    case "speech":
      if (event.role && event.text) {
        opts.onSpeech?.(
          event.role,
          event.text,
          (event.kind ?? "statement") as SpeechKind,
          event.round ?? 0,
        )
      }
      break
    case "speech_end":
      if (event.role) {
        opts.onSpeechEnd?.(
          event.role,
          (event.kind ?? "statement") as SpeechKind,
          event.round ?? 0,
        )
      }
      break
    case "tool_call":
      if (event.role && event.tool) {
        opts.onToolCall?.(
          event.role,
          event.tool,
          event.input || "",
          event.round ?? 0,
        )
      }
      break
    case "tool_result":
      if (event.role && event.tool) {
        opts.onToolResult?.(
          event.role,
          event.tool,
          event.output || "",
          event.round ?? 0,
        )
      }
      break
    case "user_question":
      if (event.question_id) {
        opts.onUserQuestion?.({
          question_id: event.question_id,
          question: event.question || "",
          context: event.context || "",
          round: event.round ?? 0,
          evidence_name: event.evidence_name,
        })
      }
      break
    case "user_answer":
      opts.onUserAnswer?.(
        event.question_id || "",
        event.answer || "",
        event.round ?? 0,
      )
      break
    case "round_end":
      opts.onRoundEnd?.(event.round ?? 0)
      break
    case "verdict":
      if (event.verdict) {
        opts.onVerdict?.(event.verdict, event.round ?? 0)
      }
      break
    case "evidence_list":
      if (event.items) {
        opts.onEvidenceList?.(event.items, event.round ?? 0)
      }
      break
    case "done":
      opts.onDone?.(event.result)
      break
    case "error":
      opts.onError?.(event.message || "庭审出错")
      break
  }
}

/**
 * 提交用户对法官追问的回答。
 *
 * 当 streamTrial 收到 user_question 事件并弹出模态窗后，
 * 用户填写回答，调用本函数提交。后端收到答案后会恢复暂停的庭审流。
 */
export async function submitAnswer(
  trialId: string,
  questionId: string,
  answer: string,
): Promise<{ ok: boolean; status: string }> {
  const res = await client.post<{
    ok: boolean
    trial_id: string
    question_id: string
    status: string
  }>(`/api/expert/trial/${trialId}/answer`, {
    question_id: questionId,
    answer,
  })
  return { ok: res.data.ok, status: res.data.status }
}

/** 获取历史庭审记录 */
export async function getTrial(trialId: string): Promise<TrialResult> {
  const res = await client.get<TrialResult>(`/api/expert/trial/${trialId}`)
  return res.data
}

/** 专家会诊健康检查 */
export async function checkExpertHealth(): Promise<{
  ok: boolean
  llm_available: boolean
}> {
  const res = await client.get("/api/expert/health")
  return res.data
}
