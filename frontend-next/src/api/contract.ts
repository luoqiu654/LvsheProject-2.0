import client from "./client"

// ========== 类型定义（内联，避免修改 types/contract.ts） ==========

// 风险等级
export type RiskLevel = "high" | "medium" | "low"

// 流水线阶段
export type PipelineStageName =
  | "parse"
  | "vision"
  | "diagnose"
  | "annotate"
  | "image"

// 单个风险点
export interface RiskPoint {
  id: string
  clause_text: string
  risk_level: RiskLevel
  risk_type: string
  description: string
  suggestion: string
}

// 流水线进度事件
export interface PipelineStageEvent {
  stage: PipelineStageName
  status: "pending" | "running" | "done" | "error" | "skipped"
  message: string
  progress: number
}

// 流水线最终结果
export interface PipelineResult {
  review_id: string
  user_id: string
  original_filename: string
  extracted_text: string
  risk_points: RiskPoint[]
  annotated_filename: string
  annotated_path: string
  summary_image_filename: string
  summary_image_path: string
  summary: string
  stages: PipelineStageEvent[]
  high_risk_count: number
  medium_risk_count: number
  low_risk_count: number
  success: boolean
  error: string
}

// 历史审查记录（精简）
export interface ReviewRecord {
  review_id: string
  user_id: string
  original_filename: string
  created_at: string
  success: boolean
  summary: string
  risk_count: number
  high_risk_count: number
  medium_risk_count: number
  low_risk_count: number
  annotated_filename: string
  summary_image_filename: string
  risk_points: RiskPoint[]
}

// 历史审查列表响应
export interface ReviewListResponse {
  ok: boolean
  user_id: string
  total: number
  reviews: ReviewRecord[]
}

// ========== URL 构造 ==========

// 预览页面 URL（独立 HTML，可 window.open 新窗口打开）
export function previewUrl(reviewId: string, userId?: string): string {
  const q = userId ? `?user_id=${encodeURIComponent(userId)}` : ""
  return `/api/contract/preview/${reviewId}${q}`
}

// 下载 URL
export function downloadUrl(reviewId: string, userId?: string): string {
  const q = userId ? `?user_id=${encodeURIComponent(userId)}` : ""
  return `/api/contract/download/${reviewId}${q}`
}

// 风险摘要图 URL
export function summaryImageUrl(reviewId: string, userId?: string): string {
  const q = userId ? `?user_id=${encodeURIComponent(userId)}` : ""
  return `/api/contract/summary-image/${reviewId}${q}`
}

// ========== SSE 流式视觉审查 ==========

export interface VisualReviewHandlers {
  onStage?: (event: PipelineStageEvent) => void
  onDone?: (result: PipelineResult) => void
  onError?: (err: string) => void
}

// 上传合同并启动视觉 AI 流水线（SSE 流式进度）
export async function visualReview(
  file: File,
  userId: string,
  handlers: VisualReviewHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const formData = new FormData()
  formData.append("file", file)
  formData.append("user_id", userId)

  let response: Response
  try {
    response = await fetch("/api/contract/visual-review", {
      method: "POST",
      body: formData,
      signal,
    })
  } catch (e: unknown) {
    if (e instanceof Error && e.name === "AbortError") return
    handlers.onError?.(e instanceof Error ? e.message : "网络请求失败")
    return
  }

  if (!response.ok || !response.body) {
    handlers.onError?.(`HTTP ${response.status}`)
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
          return
        }
        try {
          const obj = JSON.parse(payload)
          if (obj.error) {
            handlers.onError?.(obj.error)
            if (obj.result) handlers.onDone?.(obj.result as PipelineResult)
            return
          }
          if (obj.done && obj.result) {
            handlers.onDone?.(obj.result as PipelineResult)
            return
          }
          if (obj.stage) {
            handlers.onStage?.(obj as PipelineStageEvent)
          }
        } catch {
          // 忽略无法解析的行
        }
      }
    }
  } catch (e: unknown) {
    if (e instanceof Error && e.name === "AbortError") return
    handlers.onError?.(e instanceof Error ? e.message : "流式读取失败")
  }
}

// ========== 历史审查记录 ==========

export async function listReviews(userId: string): Promise<ReviewListResponse> {
  const res = await client.get<ReviewListResponse>(
    `/api/contract/reviews/${encodeURIComponent(userId)}`,
  )
  return res.data
}
