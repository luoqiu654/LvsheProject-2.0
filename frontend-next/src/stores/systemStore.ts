import { create } from "zustand"
import client from "@/api/client"

// 后端系统状态
export interface SystemStatus {
  modules?: Record<string, boolean>
  available_llm_providers?: string[]
  [key: string]: unknown
}

interface SystemState {
  // 后端地址
  backendUrl: string
  // 后端状态
  status: SystemStatus | null
  loading: boolean
  error: string | null
  // 设置后端地址
  setBackendUrl: (url: string) => void
  // 拉取后端状态
  fetchStatus: () => Promise<void>
}

export const useSystemStore = create<SystemState>()((set) => ({
  backendUrl: "http://127.0.0.1:8001",
  status: null,
  loading: false,
  error: null,
  setBackendUrl: (url) => set({ backendUrl: url }),
  fetchStatus: async () => {
    set({ loading: true, error: null })
    try {
      const res = await client.get("/api/status")
      set({ status: res.data as SystemStatus, loading: false })
    } catch (e) {
      set({ error: (e as Error).message, loading: false })
    }
  },
}))
