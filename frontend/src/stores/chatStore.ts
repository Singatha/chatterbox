import { create } from 'zustand'
import type { ReceiptEventData } from '../realtime/events'
import type { Message } from '../types/chat'

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting'

export interface PresenceState {
  online: boolean
  lastSeen: string | null
}

interface ChatState {
  selectedConversationId: string | null
  connectionStatus: ConnectionStatus
  realtimeMessages: Record<string, Message[]>
  presence: Record<string, PresenceState>
  typingUsers: Record<string, string[]>
  receiptUpdates: Record<string, ReceiptEventData>
  selectConversation: (conversationId: string | null) => void
  setConnectionStatus: (status: ConnectionStatus) => void
  addRealtimeMessage: (message: Message) => void
  setPresenceSnapshot: (onlineUserIds: string[]) => void
  setPresence: (userId: string, online: boolean, lastSeen?: string) => void
  setTyping: (conversationId: string, userId: string, typing: boolean) => void
  updateReceipt: (receipt: ReceiptEventData) => void
  clearRealtimeState: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  selectedConversationId: null,
  connectionStatus: 'disconnected',
  realtimeMessages: {},
  presence: {},
  typingUsers: {},
  receiptUpdates: {},
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
  setPresenceSnapshot: (onlineUserIds) => set((state) => {
    const presence = Object.fromEntries(
      Object.entries(state.presence).map(([userId, value]) => [
        userId,
        { ...value, online: false },
      ]),
    )
    for (const userId of onlineUserIds) {
      presence[userId] = { online: true, lastSeen: presence[userId]?.lastSeen ?? null }
    }
    return { presence }
  }),
  setPresence: (userId, online, lastSeen) => set((state) => ({
    presence: {
      ...state.presence,
      [userId]: {
        online,
        lastSeen: lastSeen ?? state.presence[userId]?.lastSeen ?? null,
      },
    },
  })),
  setTyping: (conversationId, userId, typing) => set((state) => {
    const users = state.typingUsers[conversationId] ?? []
    const next = typing
      ? users.includes(userId) ? users : [...users, userId]
      : users.filter((id) => id !== userId)
    return { typingUsers: { ...state.typingUsers, [conversationId]: next } }
  }),
  updateReceipt: (receipt) => set((state) => ({
    receiptUpdates: { ...state.receiptUpdates, [receipt.message_id]: receipt },
  })),
  clearRealtimeState: () => set({
    connectionStatus: 'disconnected',
    realtimeMessages: {},
    presence: {},
    typingUsers: {},
    receiptUpdates: {},
  }),
}))
