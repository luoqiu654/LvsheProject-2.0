import { useCallback, useEffect, useRef, useState } from "react"
import {
  Plus,
  Send,
  Trash2,
  Square,
  BookOpen,
  Sparkles,
  Paperclip,
  X,
  Loader,
  FileText,
  Image as ImageIcon,
} from "lucide-react"
import { useChatStore } from "@/stores/chatStore"
import { streamMultiTurn, getModels, type ModelsInfo } from "@/api/chat"
import { analyzeImage, parseDocument } from "@/api/files"
import type { Attachment } from "@/types/chat"
import type { Message } from "@/types/chat"
import { MarkdownRenderer } from "@/components/shared/MarkdownRenderer"
import { ThinkingPanel } from "@/components/shared/ThinkingPanel"
import { cn } from "@/lib/utils"

// 允许上传的文件类型
const ACCEPTED_TYPES =
  ".txt,.md,.pdf,.docx,.png,.jpg,.jpeg"
const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB

// 输入区待发送附件（含解析状态与内容）
interface PendingAttachment {
  id: string
  name: string
  size: number
  kind: "text" | "image" | "doc"
  status: "loading" | "ready" | "error"
  content: string // text/doc: 提取文本; image: base64 DataURL
  visionDescription?: string // 图片经视觉模型分析后的描述
  errorMessage?: string
}

// 判断文件类型
function detectKind(
  file: File,
): PendingAttachment["kind"] {
  const name = file.name.toLowerCase()
  if (/\.(png|jpe?g)$/.test(name)) return "image"
  if (/\.(pdf|docx)$/.test(name)) return "doc"
  return "text"
}

// 格式化文件大小
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

const SYSTEM_PROMPT =
  "你是绿社法律 AI 助手，一个严谨、专业、友好的中文法律咨询助手。" +
  "请用清晰易懂的语言回答用户的法律问题，必要时引用相关法律条文。" +
  "回答使用 Markdown 格式，重点内容加粗。"

export default function Chat() {
  const {
    conversations,
    currentConversationId,
    isStreaming,
    selectedModel,
    useRag,
    createConversation,
    setCurrentConversation,
    addMessage,
    updateMessage,
    deleteConversation,
    setStreaming,
    setSelectedModel,
    setUseRag,
    renameConversation,
  } = useChatStore()

  const [input, setInput] = useState("")
  const [models, setModels] = useState<ModelsInfo | null>(null)
  const [pendingAttachments, setPendingAttachments] = useState<
    PendingAttachment[]
  >([])
  // 附件 ID -> 视觉分析描述（用于在用户消息下展示"AI视觉分析"卡片）
  const [visionAnalysis, setVisionAnalysis] = useState<Record<string, string>>(
    {},
  )
  // AI 消息 ID -> 思考步骤列表（折叠展示）
  const [thinkingByMsg, setThinkingByMsg] = useState<Record<string, string[]>>(
    {},
  )
  // AI 消息 ID -> 生成的图片 URL 列表（GLM-Image 生成结果）
  const [generatedImages, setGeneratedImages] = useState<
    Record<string, string[]>
  >({})
  const abortRef = useRef<AbortController | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 获取模型列表
  useEffect(() => {
    getModels().then(setModels).catch(() => {})
  }, [])

  // 默认模型
  useEffect(() => {
    if (models && !selectedModel) {
      setSelectedModel(models.default_model)
    }
  }, [models, selectedModel, setSelectedModel])

  // 自动滚动到底部
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [])

  // 当前对话
  const currentConversation = conversations.find(
    (c) => c.id === currentConversationId,
  )

  // 自动滚动
  useEffect(() => {
    scrollToBottom()
  }, [currentConversation?.messages, scrollToBottom])

  // 自动调整 textarea 高度
  useEffect(() => {
    const ta = textareaRef.current
    if (ta) {
      ta.style.height = "auto"
      ta.style.height = Math.min(ta.scrollHeight, 200) + "px"
    }
  }, [input])

  // 更新单个待发送附件状态
  const updatePending = useCallback(
    (id: string, patch: Partial<PendingAttachment>) => {
      setPendingAttachments((prev) =>
        prev.map((a) => (a.id === id ? { ...a, ...patch } : a)),
      )
    },
    [],
  )

  // 处理单个文件：文本直读、图片转 base64 后调视觉接口、PDF/DOCX 调解析接口
  const processFile = useCallback(
    async (file: File, id: string) => {
      const kind = detectKind(file)
      try {
        if (kind === "text") {
          const text = await file.text()
          // 限制注入文本长度，避免超长上下文
          const trimmed =
            text.length > 8000 ? text.slice(0, 8000) + "\n...(内容已截断)" : text
          updatePending(id, {
            status: "ready",
            content: trimmed,
          })
        } else if (kind === "image") {
          const dataUrl = await new Promise<string>((resolve, reject) => {
            const reader = new FileReader()
            reader.onload = () => resolve(reader.result as string)
            reader.onerror = () => reject(new Error("图片读取失败"))
            reader.readAsDataURL(file)
          })
          // 保持 loading 状态直到视觉分析完成，避免发送时尚无分析结果
          updatePending(id, { status: "loading", content: dataUrl })
          // 调用后端 GLM-OCR 视觉模型分析图片内容
          try {
            const result = await analyzeImage(dataUrl)
            const desc = result?.description || ""
            updatePending(id, {
              status: "ready",
              visionDescription: desc,
            })
            if (desc) {
              setVisionAnalysis((prev) => ({ ...prev, [id]: desc }))
            }
          } catch {
            // 视觉接口不可用时仍允许发送（无分析卡片）
            updatePending(id, { status: "ready" })
          }
        } else {
          // doc: 调后端解析
          updatePending(id, { status: "loading" })
          try {
            const result = await parseDocument(file)
            const text = result?.text || ""
            const trimmed =
              text.length > 8000 ? text.slice(0, 8000) + "\n...(内容已截断)" : text
            updatePending(id, { status: "ready", content: trimmed })
          } catch (e) {
            updatePending(id, {
              status: "error",
              errorMessage:
                e instanceof Error ? e.message : "文档解析失败",
            })
          }
        }
      } catch (e) {
        updatePending(id, {
          status: "error",
          errorMessage: e instanceof Error ? e.message : "文件处理失败",
        })
      }
    },
    [updatePending],
  )

  // 选择文件
  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files
      if (!files || files.length === 0) return
      for (const file of Array.from(files)) {
        if (file.size > MAX_FILE_SIZE) {
          alert(`文件 ${file.name} 超过 10MB 限制`)
          continue
        }
        const id = crypto.randomUUID()
        const pending: PendingAttachment = {
          id,
          name: file.name,
          size: file.size,
          kind: detectKind(file),
          status: "loading",
          content: "",
        }
        setPendingAttachments((prev) => [...prev, pending])
        void processFile(file, id)
      }
      // 清空 input 以便重复选择同一文件
      if (fileInputRef.current) fileInputRef.current.value = ""
    },
    [processFile],
  )

  // 移除附件
  const removeAttachment = useCallback((id: string) => {
    setPendingAttachments((prev) => prev.filter((a) => a.id !== id))
  }, [])

  // 点击附件按钮
  const handleAttachClick = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  // 发送消息
  const handleSend = useCallback(async () => {
    const text = input.trim()
    const readyAttachments = pendingAttachments.filter(
      (a) => a.status === "ready",
    )
    const hasLoading = pendingAttachments.some((a) => a.status === "loading")
    // 附件仍在解析中时不允许发送
    if (hasLoading) return
    // 至少要有文本或就绪附件
    if (!text && readyAttachments.length === 0) return
    if (isStreaming) return

    // 构建注入后端的内容：在文本前附上文件摘要
    // 图片附件发送 data URL，后端通过 /api/chat/multi-turn 编排视觉模型分析
    const fileContextParts: string[] = []
    for (const att of readyAttachments) {
      if (att.kind === "image") {
        // 发送图片 data URL，后端将调用 GLM-OCR 视觉模型分析并注入结果
        fileContextParts.push(
          `[附件图片: ${att.name}]\n图片数据：${att.content}\n[/附件图片]`,
        )
      } else {
        fileContextParts.push(
          `[附件文件: ${att.name}]\n${att.content}\n[/附件文件]`,
        )
      }
    }
    const injectedContent =
      fileContextParts.length > 0
        ? `${fileContextParts.join("\n\n")}\n\n${text}`
        : text

    // 用于展示在气泡里的内容（去掉文件正文，保留文件名标注，避免气泡过长）
    const displayParts: string[] = []
    for (const att of readyAttachments) {
      displayParts.push(`[附件] ${att.name}`)
    }
    const displayContent =
      displayParts.length > 0
        ? `${displayParts.join("\n")}\n${text}`
        : text

    // 确保有对话
    const titleBase = text || readyAttachments[0]?.name || "新对话"
    let convId = currentConversationId
    if (!convId) {
      convId = createConversation(titleBase.slice(0, 20))
    } else if (currentConversation?.messages.length === 0) {
      // 重命名空对话
      renameConversation(convId, titleBase.slice(0, 20))
    }

    if (!convId) return

    // 添加用户消息
    const msgAttachments: Attachment[] = readyAttachments.map((a) => ({
      id: a.id,
      name: a.name,
      type: a.kind,
      size: a.size,
      url: a.kind === "image" ? a.content : undefined,
    }))
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: displayContent,
      createdAt: new Date().toISOString(),
      attachments: msgAttachments,
    }
    addMessage(convId, userMsg)
    setInput("")
    setPendingAttachments([])
    setStreaming(true)

    // 准备消息历史（发给后端）
    const history = currentConversation?.messages ?? []
    const apiMessages = [
      { role: "system", content: SYSTEM_PROMPT },
      ...history.map((m) => ({ role: m.role, content: m.content })),
      { role: "user", content: injectedContent },
    ]

    // 创建 AI 消息占位
    const aiMsgId = crypto.randomUUID()
    const aiMsg: Message = {
      id: aiMsgId,
      role: "assistant",
      content: "",
      createdAt: new Date().toISOString(),
      attachments: [],
    }
    addMessage(convId, aiMsg)

    const controller = new AbortController()
    abortRef.current = controller

    // ===== 统一流式回复分支 =====
    // 后端 /api/chat/multi-turn 负责编排：
    //   1. 检测图片生成关键词 → 调用 GLM-Image
    //   2. 检测图片附件 → 调用 GLM-OCR 视觉模型
    //   3. 正常多轮对话 → chat_stream_with_reasoning
    let accumulated = ""

    await streamMultiTurn(apiMessages, {
      model: selectedModel || undefined,
      use_rag: useRag,
      max_tokens: 4096,
      signal: controller.signal,
      onThinking: (t) => {
        setThinkingByMsg((prev) => {
          const arr = prev[aiMsgId] || []
          // 避免重复追加相同步骤
          if (arr[arr.length - 1] === t) return prev
          return { ...prev, [aiMsgId]: [...arr, t] }
        })
      },
      onImage: (url) => {
        // 后端 GLM-Image 生成的图片 URL
        setGeneratedImages((prev) => ({
          ...prev,
          [aiMsgId]: [...(prev[aiMsgId] || []), url],
        }))
      },
      onChunk: (chunk) => {
        accumulated += chunk
        updateMessage(convId!, aiMsgId, accumulated)
      },
      onDone: () => {
        setStreaming(false)
        abortRef.current = null
      },
      onError: (err) => {
        accumulated += `\n\n⚠️ ${err}`
        updateMessage(convId!, aiMsgId, accumulated)
        setStreaming(false)
        abortRef.current = null
      },
    })
  }, [
    input,
    isStreaming,
    pendingAttachments,
    currentConversationId,
    currentConversation,
    selectedModel,
    useRag,
    createConversation,
    addMessage,
    updateMessage,
    setStreaming,
    setPendingAttachments,
    setThinkingByMsg,
    setGeneratedImages,
    renameConversation,
  ])

  // 停止生成
  const handleStop = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setStreaming(false)
  }, [setStreaming])

  // 键盘事件
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // 新建对话
  const handleNewChat = () => {
    if (isStreaming) handleStop()
    createConversation()
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* 左侧对话列表 */}
      <div className="flex w-64 shrink-0 flex-col border-r border-gray-200 bg-white">
        <div className="p-3">
          <button
            onClick={handleNewChat}
            className="flex w-full items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-blue-700"
          >
            <Plus className="h-4 w-4" />
            新建对话
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-2">
          {conversations.length === 0 && (
            <p className="px-3 py-4 text-center text-xs text-gray-400">
              暂无对话记录
            </p>
          )}
          {conversations.map((conv) => (
            <div
              key={conv.id}
              onClick={() => setCurrentConversation(conv.id)}
              className={cn(
                "group mb-1 flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm transition",
                conv.id === currentConversationId
                  ? "bg-blue-50 text-blue-700"
                  : "text-gray-600 hover:bg-gray-100",
              )}
            >
              <Sparkles className="h-3.5 w-3.5 shrink-0 opacity-50" />
              <span className="flex-1 truncate">{conv.title}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  deleteConversation(conv.id)
                }}
                className="opacity-0 transition group-hover:opacity-100"
              >
                <Trash2 className="h-3.5 w-3.5 text-gray-400 hover:text-red-500" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* 右侧聊天区 */}
      <div className="flex flex-1 flex-col overflow-hidden bg-gray-50">
        {/* 顶部工具栏 */}
        <div className="flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-2">
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            className="rounded-md border border-gray-300 bg-white px-2 py-1 text-sm text-gray-700 focus:border-blue-500 focus:outline-none"
          >
            {models?.text_models?.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <button
            onClick={() => setUseRag(!useRag)}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-3 py-1 text-sm font-medium transition",
              useRag
                ? "bg-green-100 text-green-700"
                : "bg-gray-100 text-gray-500 hover:bg-gray-200",
            )}
            title="启用后将从法律知识库检索相关条文增强回答"
          >
            <BookOpen className="h-3.5 w-3.5" />
            {useRag ? "知识库增强已开启" : "知识库增强"}
          </button>
          <div className="ml-auto text-xs text-gray-400">
            {isStreaming && "正在生成..."}
          </div>
        </div>

        {/* 消息列表 */}
        <div className="flex-1 overflow-y-auto px-4 py-6">
          {currentConversation && currentConversation.messages.length > 0 ? (
            <div className="mx-auto max-w-3xl space-y-6">
              {currentConversation.messages.map((msg) => (
                <div
                  key={msg.id}
                  className={cn(
                    "flex gap-3",
                    msg.role === "user" ? "flex-row-reverse" : "",
                  )}
                >
                  {/* 头像 */}
                  <div
                    className={cn(
                      "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white",
                      msg.role === "user" ? "bg-blue-600" : "bg-emerald-600",
                    )}
                  >
                    {msg.role === "user" ? "我" : "AI"}
                  </div>
                  {/* 气泡 */}
                  <div
                    className={cn(
                      "flex-1 overflow-hidden",
                      msg.role === "user" ? "flex justify-end" : "",
                    )}
                  >
                    {msg.role === "user" ? (
                      <div className="flex flex-col items-end gap-2">
                        {/* 附件图片缩略图 */}
                        {msg.attachments && msg.attachments.length > 0 && (
                          <div className="flex flex-wrap justify-end gap-2">
                            {msg.attachments.map((att) =>
                              att.type === "image" && att.url ? (
                                <img
                                  key={att.id}
                                  src={att.url}
                                  alt={att.name}
                                  className="h-24 w-24 rounded-lg border border-white/30 object-cover shadow"
                                />
                              ) : (
                                <div
                                  key={att.id}
                                  className="flex items-center gap-1.5 rounded-lg bg-white/15 px-2.5 py-1.5 text-xs text-white"
                                >
                                  <FileText className="h-3.5 w-3.5" />
                                  <span className="max-w-[140px] truncate">
                                    {att.name}
                                  </span>
                                </div>
                              ),
                            )}
                          </div>
                        )}
                        <div className="inline-block whitespace-pre-wrap rounded-2xl rounded-tr-sm bg-blue-600 px-4 py-2.5 text-sm text-white">
                          {msg.content}
                        </div>
                        {/* AI 视觉分析卡片（GLM-OCR 分析结果，可折叠） */}
                        {(() => {
                          const steps = (msg.attachments || [])
                            .filter(
                              (att) =>
                                att.type === "image" && visionAnalysis[att.id],
                            )
                            .map(
                              (att) =>
                                `📎 ${att.name}：\n${visionAnalysis[att.id]}`,
                            )
                          if (steps.length === 0) return null
                          return (
                            <div className="w-full max-w-md">
                              <ThinkingPanel
                                variant="vision"
                                title="AI视觉分析（GLM-OCR）"
                                steps={steps}
                                defaultExpanded
                              />
                            </div>
                          )
                        })()}
                      </div>
                    ) : (
                      <div className="rounded-2xl rounded-tl-sm bg-white px-4 py-3 shadow-sm ring-1 ring-gray-100">
                        {/* 思考过程折叠面板 */}
                        {thinkingByMsg[msg.id]?.length > 0 && (
                          <ThinkingPanel
                            steps={thinkingByMsg[msg.id]}
                            active={
                              isStreaming &&
                              msg.id ===
                                currentConversation.messages[
                                  currentConversation.messages.length - 1
                                ]?.id
                            }
                          />
                        )}
                        {msg.content ? (
                          <MarkdownRenderer
                            content={msg.content}
                            className="prose prose-sm max-w-none prose-pre:bg-gray-800 prose-pre:text-gray-100 prose-code:before:hidden prose-code:after:hidden"
                          />
                        ) : (
                          <span className="inline-flex gap-1 text-gray-400">
                            <span className="h-2 w-2 animate-bounce rounded-full bg-gray-300 [animation-delay:0ms]" />
                            <span className="h-2 w-2 animate-bounce rounded-full bg-gray-300 [animation-delay:150ms]" />
                            <span className="h-2 w-2 animate-bounce rounded-full bg-gray-300 [animation-delay:300ms]" />
                          </span>
                        )}
                        {/* GLM-Image 生成的图片 */}
                        {generatedImages[msg.id]?.length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-3">
                            {generatedImages[msg.id].map((url, i) => (
                              <a
                                key={i}
                                href={url}
                                target="_blank"
                                rel="noopener noreferrer"
                                title="点击查看大图"
                              >
                                <img
                                  src={url}
                                  alt={`生成图片 ${i + 1}`}
                                  className="max-w-[16rem] rounded-lg border border-gray-200 object-contain shadow-sm transition hover:opacity-90"
                                />
                              </a>
                            ))}
                          </div>
                        )}
                        {/* 流式光标 */}
                        {isStreaming &&
                          msg.role === "assistant" &&
                          msg.content &&
                          msg.id === currentConversation.messages[currentConversation.messages.length - 1]?.id && (
                            <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-gray-400 align-middle" />
                          )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-emerald-500 text-white shadow-lg">
                <Sparkles className="h-8 w-8" />
              </div>
              <h2 className="mb-2 text-xl font-bold text-gray-800">
                绿社法律 AI 咨询
              </h2>
              <p className="mb-6 max-w-md text-sm text-gray-500">
                专业的中文法律 AI 助手，为您提供法律咨询、条文解读、案例分析。
                支持 Markdown 格式回复与多轮对话。
              </p>
              <div className="grid grid-cols-2 gap-3">
                {[
                  "劳动合同解除的条件有哪些？",
                  "民间借贷的利息上限是多少？",
                  "什么是表见代理？",
                  "违约金过高可以请求减少吗？",
                ].map((q) => (
                  <button
                    key={q}
                    onClick={() => setInput(q)}
                    className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-left text-xs text-gray-600 transition hover:border-blue-300 hover:bg-blue-50"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 输入区 */}
        <div className="border-t border-gray-200 bg-white px-4 py-3">
          <div className="mx-auto max-w-3xl">
            {/* 待发送附件列表 */}
            {pendingAttachments.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-2">
                {pendingAttachments.map((att) => (
                  <div
                    key={att.id}
                    className="group flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-1.5"
                  >
                    {att.kind === "image" && att.content ? (
                      <img
                        src={att.content}
                        alt={att.name}
                        className="h-8 w-8 rounded object-cover"
                      />
                    ) : (
                      <span className="flex h-8 w-8 items-center justify-center rounded bg-gray-200 text-gray-500">
                        {att.kind === "image" ? (
                          <ImageIcon className="h-4 w-4" />
                        ) : (
                          <FileText className="h-4 w-4" />
                        )}
                      </span>
                    )}
                    <div className="flex flex-col">
                      <span className="max-w-[160px] truncate text-xs font-medium text-gray-700">
                        {att.name}
                      </span>
                      <span className="text-[10px] text-gray-400">
                        {att.status === "loading" && "解析中..."}
                        {att.status === "ready" && formatSize(att.size)}
                        {att.status === "error" &&
                          (att.errorMessage || "解析失败")}
                      </span>
                    </div>
                    {att.status === "loading" ? (
                      <Loader className="h-3.5 w-3.5 animate-spin text-blue-500" />
                    ) : (
                      <button
                        onClick={() => removeAttachment(att.id)}
                        className="text-gray-400 transition hover:text-red-500"
                        title="移除"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}

            <div className="flex items-end gap-2">
              {/* 附件按钮 */}
              <button
                onClick={handleAttachClick}
                disabled={isStreaming}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-gray-300 bg-gray-50 text-gray-500 transition hover:bg-gray-100 hover:text-gray-700 disabled:cursor-not-allowed disabled:opacity-50"
                title="上传文件"
              >
                <Paperclip className="h-4 w-4" />
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED_TYPES}
                multiple
                onChange={handleFileSelect}
                className="hidden"
              />
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="输入您的法律问题... (Enter 发送, Shift+Enter 换行)"
                rows={1}
                className="flex-1 resize-none rounded-xl border border-gray-300 bg-gray-50 px-4 py-2.5 text-sm text-gray-800 placeholder-gray-400 focus:border-blue-500 focus:bg-white focus:outline-none"
                style={{ maxHeight: "200px" }}
              />
              {isStreaming ? (
                <button
                  onClick={handleStop}
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-red-100 text-red-600 transition hover:bg-red-200"
                  title="停止生成"
                >
                  <Square className="h-4 w-4 fill-current" />
                </button>
              ) : (
                <button
                  onClick={handleSend}
                  disabled={
                    !input.trim() &&
                    !pendingAttachments.some((a) => a.status === "ready")
                  }
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300"
                  title="发送"
                >
                  <Send className="h-4 w-4" />
                </button>
              )}
            </div>
            <p className="mt-1.5 text-[11px] text-gray-400">
              支持 .txt .md .pdf .docx .png .jpg，单文件最大 10MB
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
