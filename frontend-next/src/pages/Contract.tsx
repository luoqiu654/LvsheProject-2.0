import { useCallback, useRef, useState } from "react"
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  Eye,
  FileText,
  History,
  Image as ImageIcon,
  Loader2,
  Upload,
  UploadCloud,
  X,
  type LucideIcon,
} from "lucide-react"
import {
  downloadUrl,
  listReviews,
  summaryImageUrl,
  visualReview,
  type PipelineResult,
  type PipelineStageEvent,
  type ReviewRecord,
  type RiskLevel,
  type RiskPoint,
} from "@/api/contract"
import ContractPreview from "@/pages/ContractPreview"
import { cn } from "@/lib/utils"

// 阶段元数据
interface StageMeta {
  label: string
  icon: LucideIcon
}

const STAGE_META: Record<string, StageMeta> = {
  parse: { label: "文档解析", icon: FileText },
  vision: { label: "视觉识别", icon: Eye },
  diagnose: { label: "风险诊断", icon: AlertTriangle },
  annotate: { label: "生成批注", icon: CheckCircle2 },
  image: { label: "生成摘要图", icon: ImageIcon },
}

const STAGE_ORDER = ["parse", "vision", "diagnose", "annotate", "image"]

const RISK_STYLE: Record<
  RiskLevel,
  { label: string; bg: string; border: string; text: string; dot: string }
> = {
  high: {
    label: "高风险",
    bg: "bg-red-50",
    border: "border-red-400",
    text: "text-red-700",
    dot: "bg-red-500",
  },
  medium: {
    label: "中风险",
    bg: "bg-orange-50",
    border: "border-orange-400",
    text: "text-orange-700",
    dot: "bg-orange-500",
  },
  low: {
    label: "低风险",
    bg: "bg-yellow-50",
    border: "border-yellow-400",
    text: "text-yellow-700",
    dot: "bg-yellow-500",
  },
}

const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB

export default function Contract() {
  const [userId, setUserId] = useState("default_user")
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [stageEvents, setStageEvents] = useState<PipelineStageEvent[]>([])
  const [progress, setProgress] = useState(0)
  const [result, setResult] = useState<PipelineResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showPreview, setShowPreview] = useState(false)
  const [history, setHistory] = useState<ReviewRecord[]>([])
  const [showHistory, setShowHistory] = useState(false)

  const abortRef = useRef<AbortController | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // 校验并设置文件
  const acceptFile = useCallback((f: File | null) => {
    if (!f) return
    const ext = f.name.toLowerCase().split(".").pop() || ""
    if (ext !== "docx" && ext !== "pdf") {
      setError("仅支持 .docx 与 .pdf 格式")
      return
    }
    if (f.size > MAX_FILE_SIZE) {
      setError(`文件过大（${(f.size / 1024 / 1024).toFixed(1)}MB），最大支持 10MB`)
      return
    }
    setError(null)
    setFile(f)
    setResult(null)
    setStageEvents([])
    setProgress(0)
  }, [])

  // 拖拽处理
  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      const f = e.dataTransfer.files?.[0]
      acceptFile(f || null)
    },
    [acceptFile],
  )

  // 启动视觉流水线
  const handleStart = useCallback(async () => {
    if (!file || isProcessing) return
    setIsProcessing(true)
    setError(null)
    setResult(null)
    setStageEvents([])
    setProgress(0)

    const controller = new AbortController()
    abortRef.current = controller

    await visualReview(file, userId, {
      onStage: (event) => {
        setStageEvents((prev) => {
          // 同一阶段多次事件则替换，否则追加
          const exists = prev.find((p) => p.stage === event.stage)
          if (exists) {
            return prev.map((p) => (p.stage === event.stage ? event : p))
          }
          return [...prev, event]
        })
        setProgress(event.progress)
      },
      onDone: (res) => {
        setResult(res)
        setProgress(100)
        setIsProcessing(false)
        abortRef.current = null
        if (!res.success && res.error) {
          setError(res.error)
        }
      },
      onError: (err) => {
        setError(err)
        setIsProcessing(false)
        abortRef.current = null
      },
    })
  }, [file, userId, isProcessing])

  // 取消处理
  const handleCancel = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setIsProcessing(false)
    setError("已取消处理")
  }, [])

  // 加载历史记录
  const loadHistory = useCallback(async () => {
    try {
      const res = await listReviews(userId)
      setHistory(res.reviews || [])
      setShowHistory(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载历史记录失败")
    }
  }, [userId])

  const reviewId = result?.review_id || ""
  const riskPoints = result?.risk_points || []
  const hasSummaryImage = Boolean(result?.summary_image_filename)

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      {/* 标题 */}
      <header className="mb-8">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-emerald-500 text-white shadow">
            <FileText className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">合同诊疗</h1>
            <p className="text-sm text-gray-500">
              视觉 AI 流水线：GLM-OCR 识别 → GLM 诊断 → GLM-Image 生成摘要图
            </p>
          </div>
        </div>
      </header>

      {/* 流水线图示 */}
      <div className="mb-8 flex flex-wrap items-center gap-2 rounded-xl border border-gray-200 bg-white p-4 text-xs text-gray-600">
        {STAGE_ORDER.map((s, i) => {
          const meta = STAGE_META[s]
          const Icon = meta.icon
          return (
            <div key={s} className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 rounded-lg bg-gray-50 px-2.5 py-1.5">
                <Icon className="h-3.5 w-3.5 text-blue-500" />
                <span>{meta.label}</span>
              </div>
              {i < STAGE_ORDER.length - 1 && (
                <span className="text-gray-300">→</span>
              )}
            </div>
          )
        })}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* 左侧：上传与配置 */}
        <div className="lg:col-span-2">
          <div className="rounded-xl border border-gray-200 bg-white p-6">
            {/* 用户ID */}
            <div className="mb-4">
              <label className="mb-1.5 block text-sm font-medium text-gray-700">
                用户标识
              </label>
              <input
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                disabled={isProcessing}
                placeholder="输入用户ID（用于结果隔离）"
                className="w-full rounded-lg border border-gray-300 bg-gray-50 px-3 py-2 text-sm text-gray-800 focus:border-blue-500 focus:bg-white focus:outline-none disabled:opacity-60"
              />
            </div>

            {/* 上传区 */}
            <div
              onDragOver={(e) => {
                e.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              onClick={() => inputRef.current?.click()}
              className={cn(
                "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed py-10 transition",
                dragging
                  ? "border-blue-400 bg-blue-50"
                  : "border-gray-300 bg-gray-50 hover:border-blue-300 hover:bg-blue-50/50",
              )}
            >
              <UploadCloud
                className={cn(
                  "mb-3 h-10 w-10",
                  dragging ? "text-blue-500" : "text-gray-400",
                )}
              />
              {file ? (
                <div className="text-center">
                  <p className="text-sm font-medium text-gray-800">{file.name}</p>
                  <p className="mt-1 text-xs text-gray-500">
                    {(file.size / 1024).toFixed(1)} KB · 点击重新选择
                  </p>
                </div>
              ) : (
                <div className="text-center">
                  <p className="text-sm font-medium text-gray-700">
                    拖拽文件到此处，或点击选择
                  </p>
                  <p className="mt-1 text-xs text-gray-400">
                    支持 .docx / .pdf，最大 10MB
                  </p>
                </div>
              )}
              <input
                ref={inputRef}
                type="file"
                accept=".docx,.pdf"
                className="hidden"
                onChange={(e) => acceptFile(e.target.files?.[0] || null)}
              />
            </div>

            {/* 错误提示 */}
            {error && (
              <div className="mt-4 flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {/* 操作按钮 */}
            <div className="mt-4 flex gap-3">
              {isProcessing ? (
                <button
                  onClick={handleCancel}
                  className="flex items-center gap-2 rounded-lg bg-red-100 px-4 py-2 text-sm font-medium text-red-700 transition hover:bg-red-200"
                >
                  <X className="h-4 w-4" />
                  取消处理
                </button>
              ) : (
                <button
                  onClick={handleStart}
                  disabled={!file || !userId}
                  className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300"
                >
                  <Upload className="h-4 w-4" />
                  开始视觉诊疗
                </button>
              )}
              <button
                onClick={loadHistory}
                disabled={isProcessing}
                className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-60"
              >
                <History className="h-4 w-4" />
                历史记录
              </button>
            </div>
          </div>

          {/* 进度展示 */}
          {(isProcessing || progress > 0) && (
            <div className="mt-4 rounded-xl border border-gray-200 bg-white p-6">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-900">处理进度</h3>
                <span className="text-xs text-gray-500">{Math.round(progress)}%</span>
              </div>
              {/* 进度条 */}
              <div className="mb-4 h-2 w-full overflow-hidden rounded-full bg-gray-100">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-blue-500 to-emerald-500 transition-all duration-500"
                  style={{ width: `${progress}%` }}
                />
              </div>
              {/* 阶段列表 */}
              <div className="space-y-2">
                {STAGE_ORDER.map((s) => {
                  const meta = STAGE_META[s]
                  const Icon = meta.icon
                  const evt = stageEvents.find((e) => e.stage === s)
                  const status = evt?.status || "pending"
                  return (
                    <div
                      key={s}
                      className={cn(
                        "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition",
                        status === "running" && "bg-blue-50",
                        status === "done" && "bg-green-50",
                        status === "error" && "bg-red-50",
                        status === "skipped" && "bg-gray-50",
                        status === "pending" && "bg-gray-50/50",
                      )}
                    >
                      <div className="shrink-0">
                        {status === "running" ? (
                          <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                        ) : status === "done" ? (
                          <CheckCircle2 className="h-4 w-4 text-green-500" />
                        ) : status === "error" ? (
                          <AlertTriangle className="h-4 w-4 text-red-500" />
                        ) : (
                          <Icon className="h-4 w-4 text-gray-300" />
                        )}
                      </div>
                      <span
                        className={cn(
                          "font-medium",
                          status === "pending"
                            ? "text-gray-400"
                            : "text-gray-700",
                        )}
                      >
                        {meta.label}
                      </span>
                      {evt?.message && (
                        <span className="ml-auto truncate text-xs text-gray-500">
                          {evt.message}
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>

        {/* 右侧：结果概览 */}
        <div className="lg:col-span-1">
          {result ? (
            <div className="space-y-4">
              {/* 风险统计 */}
              <div className="rounded-xl border border-gray-200 bg-white p-5">
                <h3 className="mb-3 text-sm font-semibold text-gray-900">
                  风险概览
                </h3>
                <div className="grid grid-cols-3 gap-2">
                  <StatCard
                    label="高"
                    value={result.high_risk_count}
                    className="bg-red-500"
                  />
                  <StatCard
                    label="中"
                    value={result.medium_risk_count}
                    className="bg-orange-500"
                  />
                  <StatCard
                    label="低"
                    value={result.low_risk_count}
                    className="bg-yellow-500"
                  />
                </div>
                {result.summary && (
                  <p className="mt-3 line-clamp-4 text-xs leading-relaxed text-gray-600">
                    {result.summary}
                  </p>
                )}
              </div>

              {/* 操作 */}
              <div className="rounded-xl border border-gray-200 bg-white p-5">
                <h3 className="mb-3 text-sm font-semibold text-gray-900">
                  下载与预览
                </h3>
                <div className="space-y-2">
                  <button
                    onClick={() => setShowPreview(true)}
                    className="flex w-full items-center gap-2 rounded-lg bg-blue-50 px-3 py-2 text-sm font-medium text-blue-700 transition hover:bg-blue-100"
                  >
                    <Eye className="h-4 w-4" />
                    预览批注文档
                  </button>
                  <a
                    href={downloadUrl(reviewId, userId)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex w-full items-center gap-2 rounded-lg bg-green-50 px-3 py-2 text-sm font-medium text-green-700 transition hover:bg-green-100"
                  >
                    <Download className="h-4 w-4" />
                    下载批注文档
                  </a>
                  {hasSummaryImage && (
                    <a
                      href={summaryImageUrl(reviewId, userId)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex w-full items-center gap-2 rounded-lg bg-purple-50 px-3 py-2 text-sm font-medium text-purple-700 transition hover:bg-purple-100"
                    >
                      <ImageIcon className="h-4 w-4" />
                      查看风险摘要图
                    </a>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-gray-200 bg-white/50 p-8 text-center">
              <FileText className="mx-auto mb-3 h-10 w-10 text-gray-300" />
              <p className="text-sm text-gray-400">
                上传合同并开始诊疗后，结果将显示在此处
              </p>
            </div>
          )}
        </div>
      </div>

      {/* 风险点列表 */}
      {riskPoints.length > 0 && (
        <div className="mt-6">
          <h3 className="mb-3 text-sm font-semibold text-gray-900">
            风险点清单（共 {riskPoints.length} 项）
          </h3>
          <div className="space-y-3">
            {riskPoints.map((risk, idx) => (
              <RiskCard key={risk.id || idx} risk={risk} index={idx + 1} />
            ))}
          </div>
        </div>
      )}

      {/* 历史记录抽屉 */}
      {showHistory && (
        <div
          className="fixed inset-0 z-40 bg-black/40"
          onClick={() => setShowHistory(false)}
        >
          <div
            className="absolute right-0 top-0 h-full w-96 max-w-[90vw] bg-white shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
              <h3 className="text-sm font-semibold text-gray-900">历史审查记录</h3>
              <button
                onClick={() => setShowHistory(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="max-h-[calc(100%-3rem)] overflow-y-auto p-3">
              {history.length === 0 ? (
                <p className="py-8 text-center text-sm text-gray-400">
                  暂无历史记录
                </p>
              ) : (
                history.map((r) => (
                  <HistoryCard
                    key={r.review_id}
                    record={r}
                    onPreview={(rid) => {
                      setShowHistory(false)
                      window.open(
                        `/api/contract/preview/${rid}?user_id=${encodeURIComponent(userId)}`,
                        "_blank",
                        "noopener,noreferrer",
                      )
                    }}
                  />
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* 预览覆盖层 */}
      {showPreview && result && (
        <ContractPreview
          reviewId={reviewId}
          userId={userId}
          result={result}
          onClose={() => setShowPreview(false)}
        />
      )}
    </div>
  )
}

// ========== 子组件 ==========

function StatCard({
  label,
  value,
  className,
}: {
  label: string
  value: number
  className: string
}) {
  return (
    <div className={cn("rounded-lg p-3 text-center text-white", className)}>
      <div className="text-xl font-bold">{value}</div>
      <div className="text-xs opacity-90">{label}风险</div>
    </div>
  )
}

function RiskCard({ risk, index }: { risk: RiskPoint; index: number }) {
  const level = (risk.risk_level || "medium") as RiskLevel
  const style = RISK_STYLE[level] || RISK_STYLE.medium
  return (
    <div
      className={cn(
        "rounded-lg border-l-4 bg-white p-4 shadow-sm ring-1 ring-gray-100",
        style.border,
        style.bg,
      )}
    >
      <div className="mb-2 flex items-center gap-2">
        <span
          className={cn(
            "rounded px-2 py-0.5 text-xs font-medium text-white",
            style.dot,
          )}
        >
          {style.label}
        </span>
        <span className="text-xs text-gray-400">#{index}</span>
        <span className="text-sm font-medium text-gray-800">
          {risk.risk_type || "未分类"}
        </span>
      </div>
      {risk.clause_text && (
        <div className="mb-2 rounded bg-white/70 px-3 py-2 text-xs text-gray-600">
          <span className="font-medium text-gray-500">问题条款：</span>
          {risk.clause_text}
        </div>
      )}
      {risk.description && (
        <p className="mb-2 text-sm leading-relaxed text-gray-700">
          {risk.description}
        </p>
      )}
      {risk.suggestion && (
        <p className="text-xs leading-relaxed text-green-700">
          <span className="font-medium">修改建议：</span>
          {risk.suggestion}
        </p>
      )}
    </div>
  )
}

function HistoryCard({
  record,
  onPreview,
}: {
  record: ReviewRecord
  onPreview: (reviewId: string) => void
}) {
  const date = record.created_at
    ? new Date(record.created_at).toLocaleString("zh-CN")
    : ""
  return (
    <div className="mb-2 rounded-lg border border-gray-200 p-3 transition hover:border-blue-300">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-gray-800">
            {record.original_filename || "未知文件"}
          </p>
          <p className="mt-0.5 text-xs text-gray-400">{date}</p>
        </div>
        {record.success && (
          <span className="shrink-0 rounded bg-green-100 px-1.5 py-0.5 text-[10px] font-medium text-green-700">
            完成
          </span>
        )}
      </div>
      {record.success && (
        <div className="mt-2 flex items-center gap-2 text-xs text-gray-500">
          <span>共 {record.risk_count} 项风险</span>
          {record.high_risk_count > 0 && (
            <span className="text-red-600">高 {record.high_risk_count}</span>
          )}
          {record.medium_risk_count > 0 && (
            <span className="text-orange-600">中 {record.medium_risk_count}</span>
          )}
        </div>
      )}
      {record.success && (
        <button
          onClick={() => onPreview(record.review_id)}
          className="mt-2 flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-700"
        >
          <Eye className="h-3 w-3" />
          预览
        </button>
      )}
    </div>
  )
}
