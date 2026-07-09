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
// imageBase64: 形如 "data:image/png;base64,xxxx" 的 DataURL
export async function analyzeImage(
  imageBase64: string,
  prompt?: string,
): Promise<VisionResult> {
  const res = await client.post<VisionResult>("/api/vision/analyze", {
    image: imageBase64,
    prompt:
      prompt ||
      "请详细描述这张图片的内容，特别关注其中可能涉及的法律相关信息，如合同、证件、票据、现场照片等。",
  })
  return res.data
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
