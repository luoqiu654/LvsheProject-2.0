// 合同诊疗相关的类型定义

// 合同审查风险等级
export type RiskLevel = "high" | "medium" | "low" | "info"

// 单条风险条款
export interface RiskItem {
  id: string
  clause: string
  riskLevel: RiskLevel
  description: string
  suggestion?: string
}

// 合同审查结果
export interface ContractReviewResult {
  id: string
  fileName: string
  risks: RiskItem[]
  summary: string
  createdAt: string
}
