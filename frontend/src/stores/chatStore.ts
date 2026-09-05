import { create } from 'zustand'

interface ChatState {
  selectedConversationId: string | null
  selectConversation: (conversationId: string | null) => void
}

export const useChatStore = create<ChatState>((set) => ({
  selectedConversationId: null,
  selectConversation: (selectedConversationId) => set({ selectedConversationId }),
}))

