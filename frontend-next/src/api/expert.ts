import client from "./client"

// ========== 类型定义 ==========

/** 庭审角色 */
export type TrialRole =
  | "chief_judge"   // 审判长
  | "plaintiff"     // 原告
  | "defendant"     // 被告
  | "judge"         // 中立法官
  | "verdict"       // 判决

/** 单次发言记录 */
export interface TrialSpeech {
  role: TrialRole
  content: string
  round_number: number
  timestamp: string
}

/** 单轮辩论记录 */
export interface TrialRound {
  round_number: number
  plaintiff_speech: string
  defendant_speech: string
  judge_inquiry: string
}

/** 法官判决 */
export interface TrialVerdict {
  winner: string
  plaintiff_win_rate: number
  defendant_win_rate: number
  key_points: string[]
  reasoning: string
  action_suggestions: string[]
  full_text: string
}

/** 庭审完整结果 */
export interface TrialResult {
  trial_id: string
  case: string
  opening: string
  rounds: TrialRound[]
  verdict: TrialVerdict | null
  summary: string
  speeches: TrialSpeech[]
  created_at: string
}

/** SSE 流式事件 */
export interface TrialStreamEvent {
  event: "speech_start" | "speech_chunk" | "speech_end" | "done" | "error"
  role?: TrialRole
  text?: string
  round?: number
  trial_id?: string
  result?: TrialResult
  message?: string
}

/** 庭审请求参数 */
export interface TrialParams {
  case_description: string
  rounds?: number
}

// ========== API 函数 ==========

/**
 * 启动庭审（非流式）。
 *
 * 返回完整的 TrialResult。庭审可能耗时较长（每轮 3 次 LLM 调用 + 1 次判决），
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
 * 启动庭审（SSE 流式）。
 *
 * 实时推送每个角色的发言片段，通过 onEvent 回调通知调用者。
 */
export async function streamTrial(
  params: TrialParams,
  opts: {
    signal?: AbortSignal
    onEvent: (event: TrialStreamEvent) => void
    onError?: (err: string) => void
    onDone?: (result: TrialResult | undefined) => void
  },
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
        try {
          const event: TrialStreamEvent = JSON.parse(payload)
          opts.onEvent(event)
          if (event.event === "done") {
            opts.onDone?.(event.result)
            return
          }
          if (event.event === "error") {
            opts.onError?.(event.message || "庭审出错")
            return
          }
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

/** 获取历史庭审记录 */
export async function getTrial(trialId: string): Promise<TrialResult> {
  const res = await client.get<TrialResult>(`/api/expert/trials/${trialId}`)
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
