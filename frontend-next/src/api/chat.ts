import client from "./client"

// 模型信息
export interface ModelsInfo {
  text_models: string[]
  vision_model: string
  image_model: string
  default_model: string
}

// 获取可用模型
export async function getModels(): Promise<ModelsInfo> {
  const res = await client.get<ModelsInfo>("/api/models")
  return res.data
}

// 记忆条目
export interface MemoryItem {
  id: string
  user_id: string
  content: string
  category: string
  source?: string
  metadata?: Record<string, unknown>
  created_at?: string
}

// 技能元数据
export interface SkillMeta {
  name: string
  description: string
  license?: string
  compatibility?: string
  metadata?: Record<string, unknown>
}

// GUI Agent 浏览结果
export interface BrowseResult {
  task: string
  start_url: string
  title: string
  url: string
  text_preview: string
  links: { text: string; href: string }[]
  screenshot_path: string | null
  summary: string
  steps: string[]
}

// 列出用户全部长期记忆
export async function listMemories(
  userId = "default",
): Promise<{ items: MemoryItem[]; total: number }> {
  const res = await client.get(`/api/memory/list`, {
    params: { user_id: userId },
  })
  return { items: res.data.items || [], total: res.data.total || 0 }
}

// 删除单条记忆
export async function deleteMemory(
  memoryId: string,
  userId = "default",
): Promise<void> {
  await client.delete(`/api/memory/${encodeURIComponent(memoryId)}`, {
    params: { user_id: userId },
  })
}

// 列出所有已注册技能
export async function listSkills(): Promise<{
  skills: SkillMeta[]
  total: number
}> {
  const res = await client.get(`/api/skills`)
  return { skills: res.data.skills || [], total: res.data.total || 0 }
}

// GUI Agent 浏览网页
export async function browseUrl(
  startUrl: string,
  task?: string,
): Promise<BrowseResult> {
  const res = await client.post<BrowseResult>(`/api/gui/browse`, {
    task: task || "打开网页并总结主要内容",
    start_url: startUrl,
    take_screenshot: false,
    use_llm_summary: true,
    use_browser: true,
  })
  return res.data
}

// SSE 流式多轮对话
// onChunk: 每收到一个文本片段回调
// onThinking: 收到编排步骤回调（如"分析用户输入..."、"检索法律知识库..."，离散列表）
// onReasoning: 收到 LLM reasoning_content 片段回调（模型思考过程，横向流式段落）
// onImage: 收到后端生成的图片URL回调（GLM-Image 生成结果）
// onMemory: 收到记忆检索结果回调（用于前端展示"已参考 N 条历史记忆"）
// onSkill: 收到技能匹配结果回调（用于前端展示"当前使用技能: XXX"）
// onDone: 流结束回调
// onError: 出错回调
export async function streamMultiTurn(
  messages: { role: string; content: string }[],
  opts: {
    model?: string
    temperature?: number
    max_tokens?: number
    use_rag?: boolean
    signal?: AbortSignal
  } & {
    onChunk: (text: string) => void
    onThinking?: (text: string) => void
    onReasoning?: (text: string) => void
    onImage?: (imageUrl: string) => void
    onMemory?: (info: { count: number; items: { content: string; category: string }[] }) => void
    onSkill?: (info: { name: string; description: string }) => void
    onDone?: () => void
    onError?: (err: string) => void
  },
): Promise<void> {
  const body = {
    messages,
    model: opts.model || null,
    temperature: opts.temperature ?? 0.6,
    max_tokens: opts.max_tokens ?? 2048,
    use_rag: opts.use_rag ?? false,
  }

  let response: Response
  try {
    response = await fetch("/api/chat/multi-turn", {
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
          const obj = JSON.parse(payload)
          if (obj.thinking) opts.onThinking?.(obj.thinking)
          if (obj.reasoning) opts.onReasoning?.(String(obj.reasoning))
          if (obj.text) opts.onChunk(obj.text)
          if (obj.image) opts.onImage?.(obj.image)
          if (obj.memory) opts.onMemory?.(obj.memory)
          if (obj.skill) opts.onSkill?.(obj.skill)
          if (obj.error) opts.onError?.(obj.error)
          if (obj.done) {
            opts.onDone?.()
            return
          }
        } catch {
          // 忽略无法解析的行
        }
      }
    }
    opts.onDone?.()
  } catch (e: unknown) {
    if (e instanceof Error && e.name === "AbortError") return
    opts.onError?.(e instanceof Error ? e.message : "流式读取失败")
  }
}
