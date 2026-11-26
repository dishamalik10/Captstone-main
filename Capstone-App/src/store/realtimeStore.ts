import { create } from 'zustand';

const TYPING_MS = 4000;

interface RealtimeState {
  /** True while the WebSocket is open and authenticated; polling is the fallback otherwise. */
  connected: boolean;
  online: Record<string, true>;
  /** conversationId -> time until which "typing…" is shown. */
  typingUntil: Record<string, number>;
  setConnected: (connected: boolean) => void;
  setOnline: (userIds: string[]) => void;
  setPresence: (userId: string, online: boolean) => void;
  markTyping: (conversationId: string) => void;
  clearTyping: (conversationId: string) => void;
}

export const useRealtimeStore = create<RealtimeState>((set) => ({
  connected: false,
  online: {},
  typingUntil: {},
  setConnected: (connected) => set(connected ? { connected } : { connected, online: {}, typingUntil: {} }),
  setOnline: (userIds) => set({ online: Object.fromEntries(userIds.map((id) => [id, true as const])) }),
  setPresence: (userId, online) => set((s) => {
    const next = { ...s.online };
    if (online) next[userId] = true;
    else delete next[userId];
    return { online: next };
  }),
  markTyping: (conversationId) => set((s) => ({ typingUntil: { ...s.typingUntil, [conversationId]: Date.now() + TYPING_MS } })),
  clearTyping: (conversationId) => set((s) => {
    const next = { ...s.typingUntil };
    delete next[conversationId];
    return { typingUntil: next };
  }),
}));

export const TYPING_DISPLAY_MS = TYPING_MS;
