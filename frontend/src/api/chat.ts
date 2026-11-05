import { ApiError, authorizedBlobRequest, authorizedRequest } from './client'
import type {
  Attachment,
  AttachmentUpload,
  Conversation,
  Message,
  MessagePage,
  UserPublic,
} from '../types/chat'

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
  recoverMessages: (accessToken: string, conversationId: string, after: string) =>
    authorizedRequest<MessagePage>(
      `/conversations/${conversationId}/messages?limit=100&after=${encodeURIComponent(after)}`,
      accessToken,
    ),
  sendMessage: (
    accessToken: string,
    conversationId: string,
    content: string,
    attachmentIds: string[] = [],
  ) =>
    authorizedRequest<Message>(`/conversations/${conversationId}/messages`, accessToken, {
      method: 'POST',
      body: JSON.stringify({ content, attachment_ids: attachmentIds }),
    }),
  reserveAttachment: (
    accessToken: string,
    conversationId: string,
    file: File,
  ) => authorizedRequest<AttachmentUpload>(
    `/conversations/${conversationId}/attachments`,
    accessToken,
    {
      method: 'POST',
      body: JSON.stringify({
        filename: file.name,
        mime_type: file.type,
        file_size: file.size,
      }),
    },
  ),
  completeAttachment: (accessToken: string, attachmentId: string) =>
    authorizedRequest<Attachment>(`/attachments/${attachmentId}/complete`, accessToken, {
      method: 'POST',
    }),
  uploadAttachment: async (
    accessToken: string,
    conversationId: string,
    file: File,
  ) => {
    const reservation = await chatApi.reserveAttachment(accessToken, conversationId, file)
    const uploaded = await fetch(reservation.upload_url, {
      method: 'PUT',
      headers: reservation.upload_headers,
      body: file,
    })
    if (!uploaded.ok) {
      throw new ApiError('File upload failed.', uploaded.status, 'ATTACHMENT_UPLOAD_FAILED')
    }
    return chatApi.completeAttachment(accessToken, reservation.attachment.id)
  },
  downloadAttachment: (accessToken: string, attachment: Attachment) =>
    authorizedBlobRequest(attachment.download_url, accessToken),
}
