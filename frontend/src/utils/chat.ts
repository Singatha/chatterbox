import type { Conversation } from '../types/chat'

export function conversationTitle(conversation: Conversation, currentUserId: string): string {
  if (conversation.name) return conversation.name
  return conversation.members.find((member) => member.user_id !== currentUserId)?.username ?? 'Conversation'
}

export function initials(name: string): string {
  return name.slice(0, 2).toUpperCase()
}

