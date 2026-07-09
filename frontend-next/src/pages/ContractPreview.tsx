import { useEffect, useState } from "react"
import { Download, ExternalLink, Image as ImageIcon, X } from "lucide-react"
import {
  downloadUrl,
  previewUrl,
  summaryImageUrl,
  type PipelineResult,
} from "@/api/contract"

interface ContractPreviewProps {
  reviewId: string
  userId: string
  result: PipelineResult
  onClose: () => void
}

// 预览组件：全屏覆盖层，展示批注文档预览 + 风险摘要图
// 提供"在新窗口打开"、"下载批注文档"、"查看摘要图"操作
export default function ContractPreview({
  reviewId,
  userId,
  result,
  onClose,
}: ContractPreviewProps) {
  const [showSummaryImage, setShowSummaryImage] = useState(false)

  // ESC 关闭
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])

  const preview = previewUrl(reviewId, userId)
  const download = downloadUrl(reviewId, userId)
  const summary = summaryImageUrl(reviewId, userId)
  const hasSummaryImage = Boolean(result.summary_image_filename)

  // 在新窗口打开独立 HTML 预览页
  const openInNewWindow = () => {
    window.open(preview, "_blank", "noopener,noreferrer")
  }

  // 下载批注文档
  const handleDownload = () => {
    window.open(download, "_blank", "noopener,noreferrer")
  }

  const riskCount = result.risk_points.length

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black/50">
      {/* 顶部工具栏 */}
      <div className="flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-3">
        <div className="flex-1 truncate">
          <h2 className="text-sm font-semibold text-gray-900">
            合同诊疗预览 · {result.original_filename}
          </h2>
          <p className="text-xs text-gray-500">
            共 {riskCount} 个风险点（高 {result.high_risk_count} / 中{" "}
            {result.medium_risk_count} / 低 {result.low_risk_count}）
          </p>
        </div>
        <button
          onClick={openInNewWindow}
          className="flex items-center gap-1.5 rounded-lg bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 transition hover:bg-blue-100"
          title="在新窗口/新标签页打开独立预览页"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          在新窗口打开
        </button>
        {hasSummaryImage && (
          <button
            onClick={() => setShowSummaryImage((v) => !v)}
            className="flex items-center gap-1.5 rounded-lg bg-purple-50 px-3 py-1.5 text-xs font-medium text-purple-700 transition hover:bg-purple-100"
            title="切换查看风险预警摘要图"
          >
            <ImageIcon className="h-3.5 w-3.5" />
            {showSummaryImage ? "查看批注文档" : "查看风险摘要图"}
          </button>
        )}
        <button
          onClick={handleDownload}
          className="flex items-center gap-1.5 rounded-lg bg-green-50 px-3 py-1.5 text-xs font-medium text-green-700 transition hover:bg-green-100"
          title="下载批注后的 .docx 文件"
        >
          <Download className="h-3.5 w-3.5" />
          下载批注文档
        </button>
        <button
          onClick={onClose}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
          title="关闭预览 (ESC)"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* 内容区 */}
      <div className="flex-1 overflow-hidden bg-gray-100">
        {showSummaryImage && hasSummaryImage ? (
          <div className="flex h-full items-start justify-center overflow-auto p-6">
            <div className="max-w-2xl">
              <img
                src={summary}
                alt="风险预警摘要图"
                className="w-full rounded-xl shadow-lg"
              />
              <p className="mt-3 text-center text-xs text-gray-500">
                由 GLM-Image 生成的风险预警可视化摘要图
              </p>
            </div>
          </div>
        ) : (
          <iframe
            src={preview}
            title="合同批注文档预览"
            className="h-full w-full border-0"
          />
        )}
      </div>
    </div>
  )
}
