// 专家会诊相关的类型定义

// 专家角色
export type ExpertRole = "lawyer" | "judge" | "scholar" | "mediator"

// 专家会诊意见
export interface ExpertOpinion {
  id: string
  role: ExpertRole
  content: string
  createdAt: string
}

// 会诊请求
export interface ConsultationRequest {
  question: string
  domain?: string
  roles?: ExpertRole[]
}

// 会诊结果
export interface ConsultationResult {
  id: string
  opinions: ExpertOpinion[]
  conclusion: string
  createdAt: string
}
