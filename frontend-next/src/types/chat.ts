// 聊天相关的类型定义

// 消息角色
export type Role = "user" | "assistant"

// 附件
export interface Attachment {
  id: string
  name: string
  url?: string
  type?: string
  size?: number
}

// 单条消息
export interface Message {
  id: string
  role: Role
  content: string
  createdAt: string
  attachments: Attachment[]
}

// 对话
export interface Conversation {
  id: string
  title: string
  messages: Message[]
  createdAt: string
  updatedAt: string
}
