import client from "./client"

// ====== 文件上传相关接口 ======
// 视觉模型分析：传入 base64 图片，返回图片描述
// 文档解析：传入 PDF/DOCX 文件，返回提取的文本

// 视觉分析结果
export interface VisionResult {
  description: string
  model?: string
  [key: string]: unknown
}

// 调用后端视觉模型分析图片
// imageBase64: 形如 "data:image/png;base64,xxxx" 的 DataURL，或纯 base64
export async function analyzeImage(
  imageBase64: string,
  prompt?: string,
): Promise<VisionResult> {
  // 后端 image_base64 字段需要纯 base64（不含 data: 前缀）
  const pureBase64 = imageBase64.includes(",")
    ? imageBase64.split(",")[1]
    : imageBase64
  const res = await client.post<VisionResult>("/api/vision/analyze", {
    image_base64: pureBase64,
    prompt:
      prompt ||
      "请详细描述这张图片的内容，特别关注其中可能涉及的法律相关信息，如合同、证件、票据、现场照片等。",
  })
  // 后端返回 text 字段（识别文本），统一映射为 description 供前端使用
  const data = res.data as VisionResult & { text?: string }
  return {
    ...data,
    description: data.description || data.text || "",
  }
}

// 文档解析结果
export interface DocumentParseResult {
  text: string
  filename?: string
  [key: string]: unknown
}

// 解析 PDF / DOCX 文件，返回纯文本
export async function parseDocument(
  file: File,
): Promise<DocumentParseResult> {
  const formData = new FormData()
  formData.append("file", file)
  const res = await client.post<DocumentParseResult>(
    "/api/documents/parse",
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 60000,
    },
  )
  return res.data
}

// ====== 图像生成（GLM-Image）相关接口 ======

// 图像生成结果
export interface ImageGenerateResult {
  model?: string
  image_paths: string[]
  image_count?: number
  prompt: string
  [key: string]: unknown
}

// 调用后端 GLM-Image 模型生成图片
// prompt: 图片描述提示词
// 返回生成的图片本地路径列表（可通过 /api/image/download 下载）
export async function generateImage(
  prompt: string,
  opts?: {
    size?: string
    n?: number
    user_id?: string
  },
): Promise<ImageGenerateResult> {
  const res = await client.post<ImageGenerateResult>("/api/image/generate", {
    prompt,
    size: opts?.size ?? "1024x1024",
    n: opts?.n ?? 1,
    user_id: opts?.user_id ?? "default",
  })
  return res.data
}

// 根据后端返回的 image_path 构造可访问的图片下载 URL
// filename: 后端 image_paths 中的本地路径或文件名
// userId: 与生成时一致的 user_id（默认 "default"）
export function buildImageUrl(filename: string, userId = "default"): string {
  // 兼容完整路径或纯文件名，统一取 basename
  const base =
    filename.split(/[\\/]/).pop() || filename
  return `/api/image/download?filename=${encodeURIComponent(
    base,
  )}&user_id=${encodeURIComponent(userId)}`
}
