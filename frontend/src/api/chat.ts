import { authorizedRequest } from './client'
import type { Conversation, Message, MessagePage, UserPublic } from '../types/chat'

export const chatApi = {
  searchUsers: (accessToken: string, query: string) =>
    authorizedRequest<UserPublic[]>(`/users?q=${encodeURIComponent(query)}&limit=20`, accessToken),
  listConversations: (accessToken: string) =>
    authorizedRequest<Conversation[]>('/conversations', accessToken),
  createDirect: (accessToken: string, participantId: string) =>
    authorizedRequest<Conversation>('/conversations', accessToken, {
      method: 'POST',
      body: JSON.stringify({ participant_id: participantId }),
    }),
  listMessages: (accessToken: string, conversationId: string, before: string | null) => {
    const cursor = before ? `&before=${encodeURIComponent(before)}` : ''
    return authorizedRequest<MessagePage>(
      `/conversations/${conversationId}/messages?limit=50${cursor}`,
      accessToken,
    )
  },
  sendMessage: (accessToken: string, conversationId: string, content: string) =>
    authorizedRequest<Message>(`/conversations/${conversationId}/messages`, accessToken, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),
}

