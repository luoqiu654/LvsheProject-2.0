import { create } from "zustand"
import type { Conversation, Message } from "@/types/chat"

interface ChatState {
  conversations: Conversation[]
  currentConversationId: string | null
  isStreaming: boolean
  selectedModel: string
  useRag: boolean
  createConversation: (title?: string) => string
  setCurrentConversation: (id: string) => void
  addMessage: (conversationId: string, message: Message) => void
  updateMessage: (conversationId: string, messageId: string, content: string) => void
  deleteConversation: (id: string) => void
  setStreaming: (v: boolean) => void
  setSelectedModel: (m: string) => void
  setUseRag: (v: boolean) => void
  renameConversation: (id: string, title: string) => void
}

export const useChatStore = create<ChatState>()((set) => ({
  conversations: [],
  currentConversationId: null,
  isStreaming: false,
  selectedModel: "",
  useRag: false,

  createConversation: (title) => {
    const id = crypto.randomUUID()
    const now = new Date().toISOString()
    const conversation: Conversation = {
      id,
      title: title ?? "新对话",
      messages: [],
      createdAt: now,
      updatedAt: now,
    }
    set((state) => ({
      conversations: [conversation, ...state.conversations],
      currentConversationId: id,
    }))
    return id
  },

  setCurrentConversation: (id) => set({ currentConversationId: id }),

  addMessage: (conversationId, message) =>
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id === conversationId
          ? {
              ...c,
              messages: [...c.messages, message],
              updatedAt: new Date().toISOString(),
            }
          : c,
      ),
    })),

  updateMessage: (conversationId, messageId, content) =>
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id === conversationId
          ? {
              ...c,
              messages: c.messages.map((m) =>
                m.id === messageId ? { ...m, content } : m,
              ),
            }
          : c,
      ),
    })),

  deleteConversation: (id) =>
    set((state) => ({
      conversations: state.conversations.filter((c) => c.id !== id),
      currentConversationId:
        state.currentConversationId === id ? null : state.currentConversationId,
    })),

  setStreaming: (v) => set({ isStreaming: v }),
  setSelectedModel: (m) => set({ selectedModel: m }),
  setUseRag: (v) => set({ useRag: v }),

  renameConversation: (id, title) =>
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id === id ? { ...c, title } : c,
      ),
    })),
}))
