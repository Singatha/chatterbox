export interface UserPublic {
  id: string
  username: string
  created_at: string
}

export interface ConversationMember {
  user_id: string
  username: string
  role: string
  last_seen: string | null
}

export interface MessageReceipt {
  user_id: string
  delivered_at: string | null
  read_at: string | null
}

export interface Message {
  id: string
  conversation_id: string
  sender_id: string
  sender_username: string
  content: string
  created_at: string
  edited_at: string | null
  cursor: string
  receipts: MessageReceipt[]
}

export interface Conversation {
  id: string
  type: 'direct'
  name: string | null
  created_by: string
  created_at: string
  updated_at: string
  members: ConversationMember[]
  last_message: Pick<Message, 'id' | 'sender_id' | 'sender_username' | 'content' | 'created_at'> | null
  unread_count: number
}

export interface MessagePage {
  items: Message[]
  next_cursor: string | null
}
