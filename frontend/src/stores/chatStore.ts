import { create } from 'zustand'
import type { Message } from '../types/chat'

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting'

interface ChatState {
  selectedConversationId: string | null
  connectionStatus: ConnectionStatus
  realtimeMessages: Record<string, Message[]>
  selectConversation: (conversationId: string | null) => void
  setConnectionStatus: (status: ConnectionStatus) => void
  addRealtimeMessage: (message: Message) => void
  clearRealtimeState: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  selectedConversationId: null,
  connectionStatus: 'disconnected',
  realtimeMessages: {},
  selectConversation: (selectedConversationId) => set({ selectedConversationId }),
  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
  addRealtimeMessage: (message) => set((state) => {
    const existing = state.realtimeMessages[message.conversation_id] ?? []
    if (existing.some((item) => item.id === message.id)) return state
    return {
      realtimeMessages: {
        ...state.realtimeMessages,
        [message.conversation_id]: [...existing, message],
      },
    }
  }),
  clearRealtimeState: () => set({ connectionStatus: 'disconnected', realtimeMessages: {} }),
}))

