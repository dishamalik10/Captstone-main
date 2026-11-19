import { create } from 'zustand';
import type { ChatMessage } from '@/types';
import { chatService } from '@/services';

interface ChatState {
  sessionId: string;
  messages: ChatMessage[];
  isTyping: boolean;
  sendMessage: (content: string) => void;
  loadMessages: () => Promise<void>;
  addMessage: (message: ChatMessage) => void;
  setTyping: (typing: boolean) => void;
  newChat: () => void;
}

const createSessionId = () =>
  `chat_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;

export const useChatStore = create<ChatState>((set) => ({
  sessionId: createSessionId(),
  messages: [],
  isTyping: false,

  loadMessages: async () => {
    try {
      const sessionId = useChatStore.getState().sessionId;
      set({ messages: await chatService.getMessages(sessionId) });
    } catch {
      set({ messages: [] });
    }
  },

  sendMessage: async (content) => {
    const userMsg: ChatMessage = {
      id: `m${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    };
    set((s) => ({ messages: [...s.messages, userMsg], isTyping: true }));

    try {
      const aiMsg = await chatService.sendMessage(
        content,
        useChatStore.getState().sessionId,
      );
      set((s) => ({ messages: [...s.messages, aiMsg], isTyping: false }));
    } catch (error: unknown) {
      const response = (error as {
        response?: { status?: number; data?: { detail?: unknown } };
      } | null)?.response;
      const detail = typeof response?.data?.detail === 'string'
        ? response.data.detail.toLowerCase()
        : '';
      const modelUnavailable = response?.status === 503 && detail.includes('local llm');

      set((s) => ({
        messages: [...s.messages, {
          id: `error-${Date.now()}`,
          role: 'assistant',
          content: modelUnavailable
            ? 'The local AI model is not installed yet. From Capstone_Agents, run `python -m training.download_model`, then restart the API.'
            : 'I could not reach the styling service. Please check the backend and try again.',
          timestamp: new Date().toISOString(),
        }],
        isTyping: false,
      }));
    }
  },

  addMessage: (message) => set((s) => ({ messages: [...s.messages, message] })),

  setTyping: (typing) => set({ isTyping: typing }),
  newChat: () => set({
    sessionId: createSessionId(),
    messages: [],
    isTyping: false,
  }),
}));
