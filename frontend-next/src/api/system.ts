import client from "./client"

// 系统状态
export interface SystemStatus {
  modules?: Record<string, boolean>
  available_llm_providers?: string[]
  [key: string]: unknown
}

// 获取后端系统状态
export async function getSystemStatus(): Promise<SystemStatus> {
  const res = await client.get<SystemStatus>("/api/status")
  return res.data
}
